"""Trasformata di Anscombe generalizzata (GAT).

Trasforma un rumore Poisson-gaussiano (varianza che dipende dalla luminosità) in un
rumore circa gaussiano con deviazione standard 1 ovunque, che è l'ipotesi su cui
si basano quasi tutti gli algoritmi di denoise. Dopo il denoise si torna indietro
con l'inversa "esatta non distorta" in forma chiusa (Mäkitalo e Foi, 2013), che
evita di scurire le ombre come farebbe l'inversa algebrica.
"""

from __future__ import annotations

import numpy as np

from .noise import NoiseModel

_A_MIN = 1e-7
_SQRT_3_2 = np.sqrt(1.5)


def _params(model: NoiseModel, c: int) -> tuple[float, float]:
    alpha = max(float(model.a[c]), _A_MIN)
    sigma2 = float(model.b[c]) / alpha**2  # varianza gaussiana nelle unità di Poisson
    return alpha, sigma2


def forward(linear: np.ndarray, model: NoiseModel) -> np.ndarray:
    """(H, W, 3) lineare -> dominio stabilizzato (rumore con sigma ~ 1)."""
    out = np.empty(linear.shape, dtype=np.float32)
    for c in range(3):
        alpha, sigma2 = _params(model, c)
        z = linear[..., c].astype(np.float64) / alpha
        out[..., c] = 2.0 * np.sqrt(np.maximum(z + 0.375 + sigma2, 0.0))
    return out


def inverse(stabilized: np.ndarray, model: NoiseModel) -> np.ndarray:
    """Inversa esatta non distorta (approssimazione in forma chiusa)."""
    out = np.empty(stabilized.shape, dtype=np.float32)
    for c in range(3):
        alpha, sigma2 = _params(model, c)
        d = np.maximum(stabilized[..., c].astype(np.float64), 1e-3)
        z = (
            0.25 * d**2
            + 0.25 * _SQRT_3_2 / d
            - 1.375 / d**2
            + 0.625 * _SQRT_3_2 / d**3
            - 0.125
            - sigma2
        )
        # Per valori molto piccoli la serie non vale: si usa l'inversa algebrica.
        algebraic = 0.25 * d**2 - 0.375 - sigma2
        z = np.where(d < 1.5, algebraic, z)
        out[..., c] = np.maximum(z, 0.0) * alpha
    return out


def max_value(model: NoiseModel) -> float:
    """Valore stabilizzato massimo (segnale 1 = saturazione), usato per normalizzare in [0, 1]."""
    return max(
        float(2.0 * np.sqrt(1.0 / alpha + 0.375 + sigma2)) for alpha, sigma2 in (_params(model, c) for c in range(3))
    )
