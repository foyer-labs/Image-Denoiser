"""Algoritmi neurali (DRUNet, SCUNet) eseguiti in locale con ONNX Runtime."""

from __future__ import annotations

from typing import Any, Callable

import numpy as np

from .base import Denoiser, Param

ProgressFn = Callable[[float, str], None]

_OVERLAP = 32
#: SCUNet: sovrapposizione minore (16) a parità di qualità (−0,005 dB) e un quarto di tasselli in meno.
_SCUNET_OVERLAP = 16


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
        from ..neural.tiling import adaptive_tile, run_tiled

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

        if self.spec.noise_level_input:
            # DRUNet accetta qualsiasi misura (multipla di 8): tasselli adattati alla foto, così non si
            # ricalcolano pixel inutili (fino a metà del lavoro con tasselli fissi).
            m = self.spec.multiple
            shape = (adaptive_tile(chw.shape[1], tile, _OVERLAP, m), adaptive_tile(chw.shape[2], tile, _OVERLAP, m))
            out = run_tiled(run, chw, shape, _OVERLAP, progress, label=self.label)
        else:
            # SCUNet ha finestre di attenzione fisse: tasselli quadrati della misura del modello.
            out = run_tiled(run, chw, tile, _SCUNET_OVERLAP, progress, label=self.label)
        return np.ascontiguousarray(out.transpose(1, 2, 0))


_DEVICE = Param(
    "device", "Calcolo su", "choice", "auto",
    choices={"auto": "Scheda video se disponibile (consigliato)", "cpu": "Solo processore (CPU)"},
    tooltip="Con una scheda video la rete è molte volte più veloce. «Solo processore» serve solo se la "
    "scheda video dà problemi.",
)

_TILE_TIP = (
    "La foto viene elaborata a pezzi quadrati di questa misura. Non cambia il risultato: incide solo su "
    "velocità e memoria. Se compare un errore di memoria, scegli un valore più piccolo."
)


class DRUNetDenoiser(NeuralDenoiser):
    key = "drunet"
    model_key = "drunet"
    label = "DRUNet (IA)"
    summary = "qualità massima, lento senza scheda video"
    description = (
        "Intelligenza artificiale che usa il rumore misurato in questa foto: in genere dà la qualità "
        "migliore, e i cursori funzionano come per gli altri metodi. Senza scheda video compatibile usa "
        "il processore ed è lenta (anche alcuni minuti per foto)."
    )
    params = (
        _DEVICE,
        Param(
            "tile", "Blocchi di calcolo", "choice", "512",
            choices={"256": "256 px (poca memoria)", "512": "512 px (consigliato)", "1024": "1024 px (veloce)"},
            tooltip=_TILE_TIP,
        ),
    )


class SCUNetDenoiser(NeuralDenoiser):
    key = "scunet"
    model_key = "scunet"
    label = "SCUNet (IA)"
    summary = "per JPG e foto da smartphone"
    description = (
        "Intelligenza artificiale addestrata su foto reali di fotocamere e smartphone: stima il rumore da "
        "sola. Qui «Grana» e «Macchie di colore» decidono quanto del risultato usare (1 = tutto, "
        "0 = foto originale)."
    )
    params = (
        _DEVICE,
        Param(
            "tile", "Blocchi di calcolo", "choice", "256",
            choices={"256": "256 px (consigliato)", "512": "512 px (più memoria)"},
            tooltip=_TILE_TIP,
        ),
    )
