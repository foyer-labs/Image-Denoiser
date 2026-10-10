"""Preset: impostazioni salvate in JSON, riusabili su una foto o su una cartella intera."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .settings import DenoiseSettings, Settings

PRESET_SUFFIX = ".json"


def _builtin() -> dict[str, Settings]:
    def make(**denoise) -> Settings:
        s = Settings()
        s.denoise = DenoiseSettings(**denoise)
        return s

    return {
        "Bilanciato": make(algorithm="wavelet", luma_strength=1.0, chroma_strength=1.0),
        "Delicato": make(algorithm="wavelet", luma_strength=0.6, chroma_strength=0.9, detail=0.15),
        "Forte (ISO alti)": make(algorithm="nlm", luma_strength=1.3, chroma_strength=1.5),
        "Solo colore": make(algorithm="wavelet", luma_strength=0.0, chroma_strength=1.2),
        "Neurale RAW (DRUNet)": make(algorithm="drunet", luma_strength=1.0, chroma_strength=1.0),
        "Neurale JPG (SCUNet)": make(algorithm="scunet", luma_strength=1.0, chroma_strength=1.0),
    }


BUILTIN_PRESETS = _builtin()


def user_presets_dir() -> Path:
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "Denoiser" / "preset"


def save_preset(settings: Settings, path: str | Path) -> Path:
    path = Path(path)
    if path.suffix.lower() != PRESET_SUFFIX:
        path = path.with_suffix(PRESET_SUFFIX)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_preset(path: str | Path) -> Settings:
    return Settings.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def list_presets() -> dict[str, Settings | Path]:
    """Preset predefiniti e preset dell'utente (questi ultimi caricati su richiesta)."""
    result: dict[str, Settings | Path] = dict(BUILTIN_PRESETS)
    folder = user_presets_dir()
    if folder.is_dir():
        for p in sorted(folder.glob(f"*{PRESET_SUFFIX}")):
            result[p.stem] = p
    return result


def resolve_preset(name_or_path: str) -> Settings:
    """Accetta il nome di un preset (predefinito o dell'utente) oppure il percorso di un file JSON."""
    candidate = Path(name_or_path)
    if candidate.suffix.lower() == PRESET_SUFFIX and candidate.is_file():
        return load_preset(candidate)
    available = list_presets()
    for name, value in available.items():
        if name.lower() == name_or_path.lower():
            return load_preset(value) if isinstance(value, Path) else Settings.from_dict(value.to_dict())
    raise ValueError(f"Preset «{name_or_path}» non trovato. Disponibili: {', '.join(available)}")
