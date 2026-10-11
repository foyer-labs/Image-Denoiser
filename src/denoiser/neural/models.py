"""Modelli neurali disponibili: download dalla fonte originale, verifica e conversione in ONNX.

I pesi non sono inclusi nell'applicazione: vengono scaricati una sola volta dalle release
ufficiali, controllati con un'impronta SHA-256 e convertiti in ONNX sul computer
dell'utente. Da quel momento tutto funziona offline.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import onnx

ProgressFn = Callable[[float, str], None]


@dataclass(frozen=True)
class ModelSpec:
    key: str
    label: str
    url: str
    sha256: str
    size_mb: int
    license: str
    description: str
    #: True se la rete riceve il livello di rumore come input (forza regolabile in modo naturale).
    noise_level_input: bool
    #: Multiplo richiesto per le dimensioni dei tasselli.
    multiple: int


MODELS: dict[str, ModelSpec] = {
    "drunet": ModelSpec(
        key="drunet",
        label="DRUNet",
        url="https://github.com/cszn/KAIR/releases/download/v1.0/drunet_color.pth",
        sha256="479abe3c5327dfd10ff54a80ec7d4098ca80752a5c9492cdff31cee430bec4b4",
        size_mb=125,
        license="MIT (KAIR, Kai Zhang)",
        description=(
            "Intelligenza artificiale (Zhang et al., 2021) che riceve il rumore misurato nella foto: "
            "la forza si regola come per gli altri metodi."
        ),
        noise_level_input=True,
        multiple=8,
    ),
    "scunet": ModelSpec(
        key="scunet",
        label="SCUNet",
        url="https://github.com/cszn/KAIR/releases/download/v1.0/scunet_color_real_psnr.pth",
        sha256="fa78899ba2caec9d235a900e91d96c689da71c42029230c2028b00f09f809c2e",
        size_mb=69,
        license="Apache 2.0 (SCUNet, Kai Zhang)",
        description=(
            "Intelligenza artificiale (Zhang et al., 2023) addestrata su rumore reale di fotocamere e "
            "smartphone: stima da sola il rumore; la forza miscela il risultato con l'originale."
        ),
        noise_level_input=False,
        multiple=64,
    ),
}


class ModelNotAvailableError(RuntimeError):
    """Il modello non è ancora stato scaricato."""

    def __init__(self, spec: ModelSpec):
        super().__init__(
            f"Il modello {spec.label} non è ancora stato scaricato ({spec.size_mb} MB). "
            f"Scaricalo dall'interfaccia o con: denoiser-cli modelli scarica {spec.key}"
        )
        self.spec = spec


def models_dir() -> Path:
    override = os.environ.get("DENOISER_MODELS_DIR")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "Denoiser" / "modelli"


def weights_path(spec: ModelSpec) -> Path:
    return models_dir() / Path(spec.url).name


def onnx_path(spec: ModelSpec, tile: int | None = None) -> Path:
    suffix = f"_{tile}" if tile and spec.key == "scunet" else ""
    return models_dir() / f"{spec.key}{suffix}.onnx"


def is_downloaded(spec: ModelSpec) -> bool:
    return weights_path(spec).is_file()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(spec: ModelSpec, progress: ProgressFn | None = None) -> Path:
    """Scarica i pesi, verifica l'impronta e li salva nella cartella dei modelli."""
    target = weights_path(spec)
    if target.is_file():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, suffix=".part")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as out, urllib.request.urlopen(spec.url, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if progress is not None and total:
                    progress(done / total, f"Download di {spec.label}: {done >> 20} di {total >> 20} MB")
        actual = _sha256(tmp)
        if actual != spec.sha256:
            raise RuntimeError(
                f"Il file scaricato per {spec.label} non corrisponde all'originale atteso "
                "(impronta SHA-256 diversa): è stato scartato."
            )
        tmp.replace(target)
    finally:
        if tmp.exists():
            tmp.unlink()
    return target


_CONVERT_LOCKS: dict[Path, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def ensure_onnx(spec: ModelSpec, tile: int, progress: ProgressFn | None = None) -> Path:
    """Restituisce il modello ONNX, convertendolo dai pesi originali alla prima occorrenza.

    Anteprima ed esportazione possono chiederlo insieme: un blocco per file evita due conversioni
    in parallelo, e il file definitivo compare solo quando è completo.
    """
    path = onnx_path(spec, tile)
    if path.is_file():
        return path
    if not is_downloaded(spec):
        raise ModelNotAvailableError(spec)
    with _LOCKS_GUARD:
        lock = _CONVERT_LOCKS.setdefault(path, threading.Lock())
    with lock:
        if path.is_file():  # convertito da un altro lavoro mentre si aspettava
            return path
        from .architectures import build_drunet, build_scunet
        from .checkpoint import load_state_dict

        if progress is not None:
            progress(0.0, f"Preparazione di {spec.label} (solo la prima volta)…")
        state = load_state_dict(weights_path(spec))
        model = build_drunet(state) if spec.key == "drunet" else build_scunet(state, tile)
        onnx.checker.check_model(model)
        fd, tmp_name = tempfile.mkstemp(suffix=".tmp", dir=path.parent)
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            onnx.save_model(model, str(tmp))
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)
    return path
