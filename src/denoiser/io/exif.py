"""Lettura dei metadati essenziali (fotocamera, ISO, data) usati nei nomi dei file.

La copia completa dei metadati nel file di uscita arriverà con ExifTool in una fase successiva.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

_MAKE, _MODEL = 0x010F, 0x0110
_EXIF_IFD = 0x8769
_ISO, _DATE_ORIGINAL = 0x8827, 0x9003


@dataclass
class BasicExif:
    camera: str = ""
    iso: float | None = None
    date: str = ""  # AAAAMMGG


def read_basic_exif(path: Path) -> BasicExif:
    """Legge i dati principali; funziona con JPG, TIFF e con i RAW basati su TIFF (NEF, DNG, ARW, CR2…)."""
    info = BasicExif()
    try:
        with Image.open(path) as im:
            exif = im.getexif()
    except Exception:
        return info
    make = str(exif.get(_MAKE, "")).strip("\x00 ")
    model = str(exif.get(_MODEL, "")).strip("\x00 ")
    info.camera = model if model.lower().startswith(make.lower()) else f"{make} {model}".strip()
    try:
        sub = exif.get_ifd(_EXIF_IFD)
    except Exception:
        sub = {}
    iso = sub.get(_ISO)
    if isinstance(iso, (tuple, list)):
        iso = iso[0] if iso else None
    try:
        info.iso = float(iso) if iso else None
    except (TypeError, ValueError):
        info.iso = None
    date = str(sub.get(_DATE_ORIGINAL, "")).strip("\x00 ")
    if len(date) >= 10:
        info.date = date[:10].replace(":", "")
    return info
