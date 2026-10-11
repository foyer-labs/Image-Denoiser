"""Elaborazione completa di un file (lettura -> denoise -> salvataggio), usata da CLI e GUI."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .algorithms import get_algorithm
from .bayer import denoised_sensor_data
from .image import Domain, ImageData
from .io import load_image, save_image
from .io.dng import write_bayer_dng, write_linear_dng
from .io.formats import is_supported
from .io.metadata import copy_metadata
from .io.naming import output_path, unique_path
from .pipeline import Analysis, ProgressFn, analyze, denoise_region, render, uses_sensor_stage
from .settings import Settings


@dataclass
class JobResult:
    source: Path
    output: Path | None = None
    error: str | None = None
    skipped: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error is None and not self.skipped


def collect_inputs(paths: Iterable[str | Path], recursive: bool = False) -> list[Path]:
    """Espande le cartelle nei file supportati che contengono, senza duplicati.

    I file indicati esplicitamente vengono sempre inclusi, così un eventuale errore
    (file mancante o formato non supportato) viene segnalato invece di essere ignorato.
    """
    found: list[Path] = []
    seen: set[Path] = set()
    for p in map(Path, paths):
        if p.is_dir():
            pattern = p.rglob("*") if recursive else p.glob("*")
            candidates = [c for c in sorted(pattern) if c.is_file() and is_supported(c)]
        else:
            candidates = [p]
        for c in candidates:
            key = c.resolve()
            if key not in seen:
                seen.add(key)
                found.append(c)
    return found


def settings_description(settings: Settings) -> str:
    """Testo registrato nel file di uscita per ricordare come è stata elaborata la foto."""
    return "Denoiser: " + json.dumps(
        {"denoise": settings.to_dict()["denoise"], "tone": settings.to_dict()["tone"]},
        ensure_ascii=False,
    )


def export_image(
    image: ImageData,
    analysis: Analysis,
    settings: Settings,
    destination: Path,
    progress: ProgressFn | None = None,
    notes: list[str] | None = None,
) -> Path:
    """Elabora l'intera foto, la salva nel formato scelto e copia i metadati dell'originale.

    Il file viene scritto con un nome temporaneo e rinominato solo alla fine: un'elaborazione
    interrotta (errore, annullamento, chiusura) non lascia mai un file a metà.
    """
    destination = Path(destination)
    temporary = destination.with_name(f"{destination.stem}.parziale{destination.suffix}")
    try:
        written = _write_output(image, analysis, settings, temporary, progress)
        if settings.output.copy_metadata and image.meta.source.is_file():
            if progress is not None:
                progress(1.0, "Copia dei metadati")
            problem = copy_metadata(image.meta.source, written)
            if problem and notes is not None:
                notes.append(problem)
        os.replace(written, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination


def _write_output(
    image: ImageData, analysis: Analysis, settings: Settings, destination: Path, progress: ProgressFn | None
) -> Path:
    out = settings.output
    description = settings_description(settings)
    if out.format == "dng":
        return _export_dng(image, analysis, settings, destination, description, progress)
    pixels = render(image, analysis, settings, progress=progress)
    return save_image(
        pixels,
        destination,
        out.format,
        bit_depth=out.bit_depth,
        jpeg_quality=out.jpeg_quality,
        alpha=image.alpha if out.format != "jpeg" else None,
        exif_bytes=image.meta.exif_bytes,
        description=description,
    )


def _export_dng(
    image: ImageData,
    analysis: Analysis,
    settings: Settings,
    destination: Path,
    description: str,
    progress: ProgressFn | None,
) -> Path:
    if image.domain is not Domain.LINEAR:
        raise ValueError("Il formato DNG è disponibile solo per le foto RAW: scegli TIFF, PNG o JPEG.")
    make, model = image.meta.make, image.meta.model
    exposure = settings.tone.exposure_ev
    if uses_sensor_stage(image, settings):
        # Livello 3: si salvano i dati del sensore ripuliti, il fotoritocco farà il resto.
        src = image.raw_source
        assert src is not None
        ds = settings.denoise
        active = ds.luma_strength > 0 or ds.chroma_strength > 0 or ds.hot_pixel_threshold > 0
        sensor = denoised_sensor_data(
            src.data, src.sensor_model, get_algorithm(ds.algorithm), ds, src.flip, denoise=active, progress=progress
        )
        return write_bayer_dng(destination, sensor, make, model, exposure, description)
    linear = denoise_region(image, analysis, settings, progress=progress)
    return write_linear_dng(destination, linear, make, model, exposure, description)


def process_file(
    path: str | Path,
    settings: Settings,
    converter_path: str | Path | None = None,
    use_dng_converter: bool = True,
    progress: ProgressFn | None = None,
    image: ImageData | None = None,
    analysis: Analysis | None = None,
) -> JobResult:
    path = Path(path)
    result = JobResult(source=path)
    try:
        if image is None:
            image = load_image(path, settings.develop, use_dng_converter, converter_path)
        result.notes.extend(image.meta.notes)
        destination = output_path(image.meta, settings.output, settings.denoise.algorithm)
        if destination.exists() and not settings.output.overwrite:
            destination = unique_path(destination)
        analysis = analysis or analyze(image)
        result.output = export_image(image, analysis, settings, destination, progress, result.notes)
    except Exception as exc:  # l'errore viene riportato all'utente, il batch prosegue
        result.error = str(exc) or exc.__class__.__name__
    return result
