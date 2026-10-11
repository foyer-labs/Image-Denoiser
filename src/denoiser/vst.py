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


def channel_weights(model: NoiseModel) -> np.ndarray:
    """Pesi che rendono un grigio neutro uguale su tutti i canali dopo la trasformata.

    La GAT porta ogni canale in «unità di fotoni» (≈ 2√(x/a)): con guadagni diversi per canale
    (bilanciamento del bianco) un grigio avrebbe valori diversi su R, G e B, e i suoi bordi
    finirebbero nelle componenti di colore, che il denoise del colore sfuma (aloni colorati).
    Moltiplicando per √(a_c / ā) il grigio torna neutro; il rumore del canale c vale allora w_c.
    """
    alpha = np.array([_params(model, c)[0] for c in range(3)])
    w = np.sqrt(alpha / alpha.mean())
    return np.clip(w, 0.5, 2.0)  # limite di sicurezza se un canale ha una stima degenere


def _offset(sigma2: float) -> float:
    # Valore della trasformata per un segnale nullo: tolto perché con a ≈ 0 sarebbe enorme (≈ 2√b/a)
    # e schiaccerebbe la dinamica utile dei valori passati alle reti neurali.
    return 2.0 * np.sqrt(0.375 + sigma2)


def forward(linear: np.ndarray, model: NoiseModel) -> np.ndarray:
    """(H, W, 3) lineare -> dominio stabilizzato (rumore con sigma ~ w_c, vedi :func:`channel_weights`)."""
    out = np.empty(linear.shape, dtype=np.float32)
    weights = channel_weights(model)
    for c in range(3):
        alpha, sigma2 = _params(model, c)
        z = linear[..., c].astype(np.float64) / alpha
        out[..., c] = weights[c] * (2.0 * np.sqrt(np.maximum(z + 0.375 + sigma2, 0.0)) - _offset(sigma2))
    return out


def inverse(stabilized: np.ndarray, model: NoiseModel) -> np.ndarray:
    """Inversa esatta non distorta (approssimazione in forma chiusa)."""
    out = np.empty(stabilized.shape, dtype=np.float32)
    weights = channel_weights(model)
    for c in range(3):
        alpha, sigma2 = _params(model, c)
        d = stabilized[..., c].astype(np.float64) / weights[c] + _offset(sigma2)
        d = np.maximum(d, 1e-3)
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
    weights = channel_weights(model)
    values = []
    for c in range(3):
        alpha, sigma2 = _params(model, c)
        values.append(weights[c] * (2.0 * np.sqrt(1.0 / alpha + 0.375 + sigma2) - _offset(sigma2)))
    return float(max(values))
