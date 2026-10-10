"""Algoritmi neurali (DRUNet, SCUNet) eseguiti in locale con ONNX Runtime."""

from __future__ import annotations

from typing import Any, Callable

import numpy as np

from .base import Denoiser, Param

ProgressFn = Callable[[float, str], None]

_OVERLAP = 32


class NeuralDenoiser(Denoiser):
    """Lavora su tutti e tre i canali insieme (``joint``) invece che su un canale alla volta."""

    joint = True
    model_key = ""
    margin = 64

    @property
    def spec(self):
        from ..neural.models import MODELS

        return MODELS[self.model_key]

    def is_available(self) -> bool:
        from ..neural.models import is_downloaded

        return is_downloaded(self.spec)

    @property
    def blind(self) -> bool:
        return not self.spec.noise_level_input

    def denoise(self, channel: np.ndarray, sigma: float, params: dict[str, Any]) -> np.ndarray:
        raise TypeError("Gli algoritmi neurali elaborano l'immagine a colori intera (denoise_rgb)")

    def denoise_rgb(
        self, rgb: np.ndarray, sigma: float, params: dict[str, Any], progress: ProgressFn | None = None
    ) -> np.ndarray:
        """``rgb``: (H, W, 3) con valori circa in [0, 1]; ``sigma``: rumore in quelle unità."""
        from ..neural.models import ensure_onnx
        from ..neural.runtime import get_session
        from ..neural.tiling import run_tiled

        p = self.resolve(params)
        tile = int(p["tile"])
        session = get_session(ensure_onnx(self.spec, tile, progress), p["device"])
        chw = np.ascontiguousarray(rgb.transpose(2, 0, 1), dtype=np.float32)
        if self.spec.noise_level_input:
            level = np.float32(max(sigma, 0.0))

            def run(t: np.ndarray) -> np.ndarray:
                noise_map = np.full((1, *t.shape[1:]), level, dtype=np.float32)
                return session(np.concatenate([t, noise_map])[None])[0]
        else:

            def run(t: np.ndarray) -> np.ndarray:
                return session(t[None])[0]

        out = run_tiled(run, chw, tile, _OVERLAP, progress, label=self.label)
        return np.ascontiguousarray(out.transpose(1, 2, 0))


_DEVICE = Param(
    "device", "Dispositivo", "choice", "auto",
    choices={"auto": "Automatico (GPU se disponibile)", "cpu": "Solo CPU"},
    tooltip="Con una scheda video la rete è molte volte più veloce (DirectML o CUDA).",
)


class DRUNetDenoiser(NeuralDenoiser):
    key = "drunet"
    model_key = "drunet"
    label = "DRUNet (neurale)"
    description = (
        "Rete neurale che riceve il livello di rumore misurato: in genere la qualità più alta. "
        "Lenta senza GPU. Il modello (125 MB) si scarica una volta sola."
    )
    params = (
        _DEVICE,
        Param(
            "tile", "Tassello (px)", "choice", "512",
            choices={"256": "256", "512": "512", "1024": "1024"},
            tooltip="Dimensione dei pezzi elaborati. Tasselli grandi sono più veloci ma usano più memoria della GPU.",
        ),
    )


class SCUNetDenoiser(NeuralDenoiser):
    key = "scunet"
    model_key = "scunet"
    label = "SCUNet (neurale)"
    description = (
        "Rete neurale addestrata su rumore reale di fotocamere e smartphone: adatta soprattutto "
        "ai JPG. Stima il rumore da sola; la forza (fino a 1) miscela il risultato con l'originale. "
        "Il modello (69 MB) si scarica una volta sola."
    )
    params = (
        _DEVICE,
        Param(
            "tile", "Tassello (px)", "choice", "256",
            choices={"256": "256", "512": "512"},
            tooltip="Dimensione dei pezzi elaborati. 512 è più veloce ma richiede molta più memoria.",
        ),
    )
