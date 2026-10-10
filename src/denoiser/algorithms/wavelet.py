"""Denoise con soglia sui coefficienti wavelet (come in darktable e RawTherapee)."""

from __future__ import annotations

from itertools import product
from typing import Any

import numpy as np
import pywt
from skimage.restoration import denoise_wavelet

from .base import Denoiser, Param, to_unit_range


class WaveletDenoiser(Denoiser):
    key = "wavelet"
    label = "Wavelet"
    description = (
        "Scompone l'immagine in dettagli a varie scale e attenua quelli più piccoli del rumore. "
        "Veloce, ottimo soprattutto sul rumore di colore."
    )
    params = (
        Param(
            "wavelet", "Famiglia wavelet", "choice", "sym4",
            choices={"db1": "Haar", "db2": "Daubechies 2", "sym4": "Symlet 4", "coif1": "Coiflet 1", "bior2.2": "Biortogonale 2.2"},
            tooltip="Forma delle onde usate per scomporre l'immagine. Symlet 4 è un buon compromesso.",
        ),
        Param(
            "method", "Metodo di soglia", "choice", "BayesShrink",
            choices={"BayesShrink": "BayesShrink (adattivo)", "VisuShrink": "VisuShrink (forte)"},
            tooltip="BayesShrink adatta la soglia a ogni scala e preserva più dettaglio; VisuShrink è più aggressivo.",
        ),
        Param(
            "mode", "Tipo di soglia", "choice", "soft",
            choices={"soft": "Morbida", "hard": "Netta"},
            tooltip="La soglia morbida dà risultati più naturali; quella netta conserva più contrasto ma può lasciare artefatti.",
        ),
        Param(
            "levels", "Livelli (0 = automatico)", "int", 4, 0, 8, 1,
            tooltip="Numero di scale analizzate. Più livelli agiscono anche sul rumore a grana grossa, "
            "ma rendono l'anteprima di una zona meno fedele all'esportazione.",
        ),
        Param(
            "cycle_spin", "Spostamenti anti-artefatto", "int", 1, 0, 3, 1,
            tooltip="Media di più elaborazioni leggermente spostate: riduce gli artefatti a blocchi. "
            "Il tempo cresce rapidamente (0 = 1×, 1 = 4×, 2 = 9×, 3 = 16×).",
        ),
    )
    margin = 64

    def denoise(self, channel: np.ndarray, sigma: float, params: dict[str, Any]) -> np.ndarray:
        p = self.resolve(params)
        unit, lo, scale = to_unit_range(channel)
        sigma_unit = sigma / scale
        if sigma_unit <= 0:
            return channel.copy()

        levels = p["levels"] or None
        if levels is not None:
            # Su immagini piccole (es. anteprime) i livelli possibili sono meno.
            max_levels = pywt.dwt_max_level(min(unit.shape), pywt.Wavelet(p["wavelet"]).dec_len)
            levels = max(1, min(levels, max_levels))

        def run(x: np.ndarray) -> np.ndarray:
            return denoise_wavelet(
                x,
                sigma=sigma_unit,
                wavelet=p["wavelet"],
                mode=p["mode"],
                method=p["method"],
                wavelet_levels=levels,
                rescale_sigma=True,
            )

        shifts = p["cycle_spin"]
        if shifts == 0 or min(unit.shape) <= 16 + shifts:
            out = run(unit)
        else:
            pad = 16 + shifts
            padded = np.pad(unit, pad, mode="reflect")
            acc = np.zeros_like(unit, dtype=np.float64)
            for dy, dx in product(range(shifts + 1), repeat=2):
                shifted = np.roll(padded, (dy, dx), axis=(0, 1))
                den = np.roll(run(shifted), (-dy, -dx), axis=(0, 1))
                acc += den[pad:-pad, pad:-pad]
            out = acc / (shifts + 1) ** 2
        return (out * scale + lo).astype(np.float32)
