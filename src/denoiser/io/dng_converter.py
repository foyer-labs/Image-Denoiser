"""Integrazione con Adobe DNG Converter (gratuito, eseguito in locale).

Serve come ripiego per le fotocamere che LibRaw non supporta ancora (modelli appena
usciti o formati come i NEF "alta efficienza"): il RAW viene convertito in DNG,
che LibRaw legge in modo generico, matrici colore comprese.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

#: Variabile d'ambiente per indicare un percorso non standard del convertitore.
ENV_VAR = "DENOISER_DNG_CONVERTER"

_CANDIDATES = [
    r"C:\Program Files\Adobe\Adobe DNG Converter\Adobe DNG Converter.exe",
    r"C:\Program Files (x86)\Adobe\Adobe DNG Converter\Adobe DNG Converter.exe",
    r"C:\Program Files (x86)\Adobe\Adobe DNG Converter.exe",
    "/Applications/Adobe DNG Converter.app/Contents/MacOS/Adobe DNG Converter",
]


class DngConversionError(RuntimeError):
    pass


def find_converter(explicit: str | os.PathLike | None = None) -> Path | None:
    """Cerca Adobe DNG Converter: percorso esplicito, variabile d'ambiente, percorsi standard."""
    for candidate in (explicit, os.environ.get(ENV_VAR), *_CANDIDATES):
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    found = shutil.which("Adobe DNG Converter")
    return Path(found) if found else None


def default_cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    return Path(base) / "Denoiser" / "dng-cache"


def _cache_key(src: Path) -> str:
    st = src.stat()
    raw = f"{src.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode()
    return hashlib.sha1(raw).hexdigest()[:16]


def convert_to_dng(
    src: Path,
    converter: Path,
    cache_dir: Path | None = None,
    timeout: float = 600,
) -> Path:
    """Converte ``src`` in DNG (compressione senza perdita, senza anteprima) e restituisce il percorso.

    Il risultato viene messo in cache: la stessa foto non viene riconvertita.
    """
    out_dir = (cache_dir or default_cache_dir()) / _cache_key(src)
    existing = sorted(out_dir.glob("*.dng")) if out_dir.is_dir() else []
    if existing:
        return existing[0]
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [str(converter), "-c", "-p0", "-d", str(out_dir), str(src.resolve())]
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        subprocess.run(cmd, check=False, timeout=timeout, capture_output=True, **kwargs)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DngConversionError(f"Adobe DNG Converter non è riuscito ad avviarsi: {exc}") from exc
    produced = sorted(out_dir.glob("*.dng"))
    if not produced:
        raise DngConversionError(
            "Adobe DNG Converter non ha prodotto alcun file: forse la fotocamera non è ancora "
            "supportata nemmeno dalla versione installata. Prova ad aggiornarlo."
        )
    return produced[0]
