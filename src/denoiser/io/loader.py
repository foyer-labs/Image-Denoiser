"""Caricamento universale delle immagini.

Per i RAW le strade vengono provate in cascata:
1. LibRaw (rawpy) direttamente sul file;
2. se LibRaw non lo supporta, conversione in DNG con Adobe DNG Converter (se installato)
   e lettura del DNG;
3. altrimenti un errore chiaro che spiega cosa fare.
"""

from __future__ import annotations

from pathlib import Path

from ..image import ImageData
from ..settings import DevelopSettings
from . import dng_converter
from .exif import read_basic_exif
from .formats import kind_of
from .raster import load_jpeg, load_png_or_tiff
from .raw import RawNotSupportedError, decode_raw


class UnsupportedImageError(Exception):
    """Il file non può essere aperto; il messaggio è pensato per l'utente."""


def load_image(
    path: str | Path,
    develop: DevelopSettings | None = None,
    use_dng_converter: bool = True,
    converter_path: str | Path | None = None,
) -> ImageData:
    path = Path(path)
    if not path.is_file():
        raise UnsupportedImageError(f"File non trovato: {path}")
    kind = kind_of(path)
    if kind is None:
        raise UnsupportedImageError(f"Formato non supportato: {path.suffix or path.name}")
    if kind == "jpeg":
        return load_jpeg(path)
    if kind in ("png", "tiff"):
        return load_png_or_tiff(path, kind)
    return _load_raw(path, develop, use_dng_converter, converter_path)


def _load_raw(
    path: Path,
    develop: DevelopSettings | None,
    use_dng_converter: bool,
    converter_path: str | Path | None,
) -> ImageData:
    try:
        return decode_raw(path, develop)
    except RawNotSupportedError as exc:
        reason = str(exc)

    if path.suffix.lower() == ".dng":
        raise UnsupportedImageError(f"Impossibile leggere il DNG {path.name}: {reason}")

    converter = dng_converter.find_converter(converter_path) if use_dng_converter else None
    if converter is None:
        raise UnsupportedImageError(
            f"{path.name}: {reason}\n\n"
            "Soluzioni possibili:\n"
            "• installa Adobe DNG Converter (gratuito): l'app lo userà automaticamente;\n"
            "• oppure converti il file in DNG e apri il DNG;\n"
            "• per i NEF Nikon, imposta la fotocamera su compressione «senza perdita» "
            "invece di «alta efficienza»."
        )
    try:
        dng_path = dng_converter.convert_to_dng(path, converter)
    except dng_converter.DngConversionError as exc:
        raise UnsupportedImageError(f"{path.name}: {reason}\n\n{exc}") from exc
    try:
        image = decode_raw(dng_path, develop)
    except RawNotSupportedError as exc:
        raise UnsupportedImageError(f"Anche il DNG convertito non è leggibile: {exc}") from exc

    # Il DNG ha il suo nome nella cache: per i file di uscita conta l'originale.
    image.meta.source = path
    image.meta.kind = "dng-convertito"
    image.meta.notes.append(f"Letto tramite Adobe DNG Converter ({reason})")
    if not image.meta.camera:
        info = read_basic_exif(path)
        image.meta.camera, image.meta.iso, image.meta.date = info.camera, info.iso, info.date
        image.meta.make, image.meta.model = info.make, info.model
    return image
