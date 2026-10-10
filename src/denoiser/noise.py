"""Stima del rumore direttamente dalla foto (nessun profilo per fotocamera).

Nei dati lineari di un RAW il rumore segue il modello Poisson-gaussiano:
la varianza cresce linearmente con il segnale, ``var = a * segnale + b``,
dove ``a`` dipende dal guadagno del sensore (ISO) e ``b`` dal rumore elettronico.
Qui ``a`` e ``b`` vengono stimati per ciascun canale osservando quanto "fluttuano"
i pixel nelle zone uniformi a diversi livelli di luminosità.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# Filtro di Immerkær: annulla le superfici lisce (fino al secondo ordine) e lascia passare
# il rumore. Per rumore bianco con deviazione sigma la risposta ha deviazione 6 * sigma.
_IMMERKAER = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], dtype=np.float32)
_MAD_TO_SIGMA = 1.4826


@dataclass
class NoiseModel:
    """Modello Poisson-gaussiano per canale: var = a * x + b (x in [0, 1])."""

    a: np.ndarray  # (3,)
    b: np.ndarray  # (3,)

    def std_at(self, level: np.ndarray, channel: int) -> np.ndarray:
        return np.sqrt(np.maximum(self.a[channel] * level + self.b[channel], 1e-12))


@dataclass
class NoiseProfile:
    """Rumore misurato con precisione durante lo sviluppo di un RAW (vedi "gemello di rumore")."""

    #: Modello var = a * x + b dei canali RGB lineari sviluppati.
    model: NoiseModel
    #: Deviazione del rumore di (luminanza, colore 1, colore 2) dopo la trasformata di Anscombe.
    component_sigma: np.ndarray
    #: Modello misurato sui dati grezzi del sensore, per canale R, G, B (unità normalizzate).
    sensor_model: NoiseModel | None = None


def sample_tiles(img: np.ndarray, max_pixels: int = 4_000_000, tile: int = 128) -> list[np.ndarray]:
    """Restituisce tasselli distribuiti uniformemente sull'immagine per limitare i calcoli."""
    h, w = img.shape[:2]
    if h * w <= max_pixels or h < tile or w < tile:
        return [img]
    n_tiles = max(1, max_pixels // (tile * tile))
    ratio = w / h
    ny = max(1, int(round(np.sqrt(n_tiles / ratio))))
    nx = max(1, n_tiles // ny)
    ys = np.linspace(0, h - tile, ny).astype(int)
    xs = np.linspace(0, w - tile, nx).astype(int)
    return [img[y : y + tile, x : x + tile] for y in ys for x in xs]


def _residual_and_activity(channel: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per ogni pixel: residuo di rumore (già in unità di sigma), livello medio locale, attività."""
    x = channel.astype(np.float32, copy=False)
    resid = cv2.filter2D(x, -1, _IMMERKAER, borderType=cv2.BORDER_REFLECT) / 6.0
    mean = cv2.blur(x, (5, 5), borderType=cv2.BORDER_REFLECT)
    gx = cv2.Sobel(mean, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(mean, cv2.CV_32F, 0, 1, ksize=3)
    activity = np.abs(gx) + np.abs(gy)
    # I bordi dei tasselli non sono affidabili.
    sl = (slice(3, -3), slice(3, -3))
    return resid[sl], mean[sl], activity[sl]


def estimate_sigma(channel: np.ndarray | list[np.ndarray], max_pixels: int = 4_000_000) -> float:
    """Deviazione standard di un rumore uniforme (gaussiano), stimata nelle zone più piatte.

    Accetta un canale 2D oppure una lista di tasselli 2D già campionati.
    """
    tiles = channel if isinstance(channel, list) else sample_tiles(channel, max_pixels)
    resids, acts = [], []
    for t in tiles:
        if min(t.shape) < 8:
            continue
        r, _, act = _residual_and_activity(t)
        resids.append(r.ravel())
        acts.append(act.ravel())
    if not resids:
        return 0.0
    r = np.concatenate(resids)
    act = np.concatenate(acts)
    flat = act <= np.percentile(act, 50)
    return float(_MAD_TO_SIGMA * np.median(np.abs(r[flat])))


def estimate_noise_model(linear: np.ndarray, max_pixels: int = 4_000_000) -> NoiseModel:
    """Stima a e b per ciascun canale di un'immagine RGB lineare.

    Adatta a rumore indipendente pixel per pixel; dopo la demosaicizzazione il rumore è
    correlato e questa stima lo sottovaluta (per i RAW Bayer si usa il "gemello di rumore",
    vedi :mod:`denoiser.io.raw`).
    """
    tiles = sample_tiles(linear, max_pixels)
    a = np.zeros(3)
    b = np.zeros(3)
    for c in range(3):
        a[c], b[c] = estimate_channel_model([t[..., c] for t in tiles])
    return NoiseModel(a=a, b=b)


def estimate_channel_model(tiles: list[np.ndarray], n_bins: int = 16) -> tuple[float, float]:
    """Stima (a, b) di var = a * x + b su un canale, osservando le zone uniformi a vari livelli."""
    resids, means, acts = [], [], []
    for t in tiles:
        if min(t.shape[:2]) < 8:
            continue
        r, m, act = _residual_and_activity(t)
        resids.append(r.ravel())
        means.append(m.ravel())
        acts.append(act.ravel())
    if not resids:
        return 0.0, 1e-8
    r = np.concatenate(resids)
    m = np.concatenate(means)
    act = np.concatenate(acts)
    # Escludo le alte luci vicine alla saturazione (il rumore lì viene "tagliato").
    valid = (m > 1e-4) & (m < 0.9)
    if valid.sum() < 1000:
        valid = np.ones_like(m, dtype=bool)
    r, m, act = r[valid], m[valid], act[valid]

    edges = np.unique(np.quantile(m, np.linspace(0, 1, n_bins + 1)))
    levels, variances, weights = [], [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (m >= lo) & (m <= hi)
        if sel.sum() < 200:
            continue
        act_sel = act[sel]
        flat = act_sel <= np.percentile(act_sel, 30)
        rs = r[sel][flat]
        if rs.size < 50:
            continue
        sigma = _MAD_TO_SIGMA * np.median(np.abs(rs))
        levels.append(float(np.median(m[sel][flat])))
        variances.append(float(sigma**2))
        weights.append(float(rs.size))
    return _fit_linear_variance(np.array(levels), np.array(variances), np.array(weights))


def fit_model_from_noise(levels: np.ndarray, noise: np.ndarray, n_bins: int = 24) -> tuple[float, float]:
    """Stima (a, b) da campioni di solo rumore (``noise``) osservati ai livelli ``levels``.

    Usata con il "gemello di rumore": non c'è dettaglio dell'immagine a disturbare la misura.
    """
    valid = (levels > 1e-5) & (levels < 0.95)
    if valid.sum() < 1000:
        valid = np.ones_like(levels, dtype=bool)
    lv, nz = levels[valid], noise[valid]
    edges = np.unique(np.quantile(lv, np.linspace(0, 1, n_bins + 1)))
    out_levels, variances, weights = [], [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (lv >= lo) & (lv <= hi)
        if sel.sum() < 200:
            continue
        sigma = _MAD_TO_SIGMA * np.median(np.abs(nz[sel] - np.median(nz[sel])))
        out_levels.append(float(np.median(lv[sel])))
        variances.append(float(sigma**2))
        weights.append(float(sel.sum()))
    return _fit_linear_variance(np.array(out_levels), np.array(variances), np.array(weights))


def robust_std(x: np.ndarray) -> float:
    return float(_MAD_TO_SIGMA * np.median(np.abs(x - np.median(x))))


def _fit_linear_variance(levels: np.ndarray, variances: np.ndarray, weights: np.ndarray) -> tuple[float, float]:
    """Regressione pesata var = a * livello + b con a, b >= 0."""
    if levels.size == 0:
        return 0.0, 1e-8
    if levels.size == 1:
        return 0.0, max(float(variances[0]), 1e-12)
    w = np.sqrt(weights / weights.max())
    design = np.stack([levels, np.ones_like(levels)], axis=1) * w[:, None]
    (a, b), *_ = np.linalg.lstsq(design, variances * w, rcond=None)
    if a < 0:
        a, b = 0.0, float(np.average(variances, weights=weights))
    if b < 0:
        # Solo componente di Poisson: a = sum(w*l*v) / sum(w*l*l)
        b = 0.0
        a = float(np.sum(weights * levels * variances) / np.sum(weights * levels * levels))
    return float(a), float(max(b, 1e-12))
