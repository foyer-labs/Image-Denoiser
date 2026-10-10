"""Elaborazione completa di un file (lettura -> denoise -> salvataggio), usata da CLI e GUI."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .image import ImageData
from .io import load_image, save_image
from .io.formats import is_supported
from .io.naming import output_path, unique_path
from .pipeline import Analysis, ProgressFn, analyze, render
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


def save_result(image: ImageData, pixels, settings: Settings, destination: Path) -> Path:
    out = settings.output
    return save_image(
        pixels,
        destination,
        out.format,
        bit_depth=out.bit_depth,
        jpeg_quality=out.jpeg_quality,
        alpha=image.alpha if out.format != "jpeg" else None,
        exif_bytes=image.meta.exif_bytes,
        description=settings_description(settings),
    )


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
        pixels = render(image, analysis, settings, progress=progress)
        result.output = save_result(image, pixels, settings, destination)
    except Exception as exc:  # l'errore viene riportato all'utente, il batch prosegue
        result.error = str(exc) or exc.__class__.__name__
    return result
