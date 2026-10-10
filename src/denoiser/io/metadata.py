"""Copia completa dei metadati (EXIF, XMP, IPTC, GPS, obiettivo…) con ExifTool.

ExifTool è incluso nel pacchetto per Windows; in alternativa viene cercato nel PATH
o nel percorso indicato dalla variabile d'ambiente DENOISER_EXIFTOOL.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .. import __version__

ENV_VAR = "DENOISER_EXIFTOOL"

# Tag da non copiare: l'orientamento è già applicato o scritto da noi, la descrizione
# contiene le impostazioni di denoise, le anteprime incorporate non corrispondono più.
_EXCLUDED = ("Orientation", "ImageDescription", "ThumbnailImage", "PreviewImage", "JpgFromRaw", "OtherImage")


def _bundled_candidates() -> list[Path]:
    roots = []
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).parent)
        if hasattr(sys, "_MEIPASS"):
            roots.append(Path(sys._MEIPASS))  # type: ignore[attr-defined]
    names = ("exiftool.exe", "exiftool")
    return [root / "exiftool" / name for root in roots for name in names]


def find_exiftool(explicit: str | os.PathLike | None = None) -> Path | None:
    for candidate in (explicit, os.environ.get(ENV_VAR), *_bundled_candidates()):
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    found = shutil.which("exiftool")
    return Path(found) if found else None


def copy_metadata(source: Path, target: Path, exiftool: Path | None = None) -> str | None:
    """Copia i metadati di ``source`` in ``target``. Restituisce un messaggio d'errore o None."""
    exiftool = exiftool or find_exiftool()
    if exiftool is None:
        return "ExifTool non trovato: copiati solo i metadati essenziali"
    args = ["-charset", "filename=utf8", "-overwrite_original", "-m", "-q", "-q",
            "-TagsFromFile", str(source), "-all:all"]
    args += [f"--{tag}" for tag in _EXCLUDED]
    args += [f"-Software=Denoiser {__version__}", str(target)]
    # I nomi dei file passano da un file di argomenti UTF-8: funziona anche con lettere
    # accentate su Windows.
    fd, argfile = tempfile.mkstemp(suffix=".args")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(args) + "\n")
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(
            [str(exiftool), "-@", argfile], capture_output=True, timeout=120, **kwargs
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"ExifTool non è riuscito a copiare i metadati: {exc}"
    finally:
        try:
            os.unlink(argfile)
        except OSError:
            pass
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip().splitlines()
        return "ExifTool: " + (detail[-1] if detail else f"codice {result.returncode}")
    return None
