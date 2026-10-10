"""Rimozione dei pixel caldi (punti isolati molto più luminosi dei vicini)."""

from __future__ import annotations

from typing import Callable

import cv2
import numpy as np


def remove_hot_pixels(
    pixels: np.ndarray,
    threshold: float,
    noise_std: Callable[[np.ndarray, int], np.ndarray],
) -> tuple[np.ndarray, int]:
    """Sostituisce con la mediana locale i pixel che superano i vicini di ``threshold`` volte il rumore.

    ``noise_std(livello, canale)`` restituisce la deviazione del rumore attesa a quel livello.
    Dopo la demosaicizzazione un pixel caldo si allarga a una piccola macchia, per questo
    si usa una mediana 5x5.
    """
    out = pixels.copy()
    count = 0
    for c in range(3):
        x = np.ascontiguousarray(pixels[..., c], dtype=np.float32)
        med = cv2.medianBlur(x, 5)
        hot = (x - med) > threshold * noise_std(med, c)
        count += int(hot.sum())
        out[..., c] = np.where(hot, med, x)
    return out, count
