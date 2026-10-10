"""Non-Local Means: media pesata di zone simili sparse nell'immagine (OpenCV, multithread)."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from .base import Denoiser, Param, to_unit_range

# Con norma L1 su dati a 16 bit, h ≈ sigma dà il miglior PSNR su rumore gaussiano
# (calibrato su immagini di prova con sigma tra 0.02 e 0.1).
_H_PER_SIGMA = 1.0


class NonLocalMeansDenoiser(Denoiser):
    key = "nlm"
    label = "Non-Local Means"
    description = (
        "Per ogni pixel cerca nei dintorni piccole zone simili e ne fa la media. "
        "Preserva bene trame ripetitive e bordi; più lento della wavelet."
    )
    params = (
        Param(
            "patch_size", "Dimensione zona di confronto", "choice", "7",
            choices={"3": "3 px", "5": "5 px", "7": "7 px", "9": "9 px"},
            tooltip="Zone più grandi riconoscono meglio le strutture ma ammorbidiscono i dettagli fini.",
        ),
        Param(
            "search_window", "Area di ricerca (px)", "int", 21, 7, 41, 2,
            tooltip="Quanto lontano cercare zone simili. Il tempo cresce con il quadrato di questo valore.",
        ),
    )

    margin = 32

    def denoise(self, channel: np.ndarray, sigma: float, params: dict[str, Any]) -> np.ndarray:
        p = self.resolve(params)
        unit, lo, scale = to_unit_range(channel)
        h = sigma / scale * 65535.0 * _H_PER_SIGMA
        if h <= 0:
            return channel.copy()
        search = int(p["search_window"]) | 1  # deve essere dispari
        u16 = np.round(unit * 65535.0).astype(np.uint16)
        out = cv2.fastNlMeansDenoising(
            u16, [float(h)], None, int(p["patch_size"]), search, cv2.NORM_L1
        )
        return (out.astype(np.float32) / 65535.0 * scale + lo).astype(np.float32)
