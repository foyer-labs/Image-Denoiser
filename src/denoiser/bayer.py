"""Livello 3: denoise sui dati grezzi del sensore Bayer, prima della demosaicizzazione.

Il mosaico Bayer viene separato nei quattro piani R, G1, G2, B (a metà risoluzione).
In ciascun piano il rumore è indipendente pixel per pixel e il suo modello è noto con
precisione, quindi dopo la trasformata di Anscombe vale esattamente 1: la forza 1
corrisponde davvero al rumore presente. I quattro piani vengono poi combinati in
una componente di luminanza e tre di colore (trasformazione ortonormale), così che
luminanza e colore si possano dosare separatamente come al livello 2.
Infine i dati ripuliti vengono riscritti nel RAW e sviluppati da LibRaw.
"""

from __future__ import annotations

import io
from typing import Callable

import cv2
import numpy as np
import rawpy

from .algorithms import Denoiser
from .noise import NoiseModel
from .settings import DenoiseSettings

# Righe: luminanza, rosso-blu, verde-magenta, differenza tra i due verdi.
# Colonne: piani nell'ordine R, G1, G2, B.
_PACKED = np.array(
    [
        [0.5, 0.5, 0.5, 0.5],
        [1 / np.sqrt(2), 0.0, 0.0, -1 / np.sqrt(2)],
        [-0.5, 0.5, 0.5, -0.5],
        [0.0, 1 / np.sqrt(2), -1 / np.sqrt(2), 0.0],
    ],
    dtype=np.float32,
)
_SQRT_3_2 = np.sqrt(1.5)


# ---------------------------------------------------------------- orientamento


def orient(arr: np.ndarray, flip: int) -> np.ndarray:
    """Applica l'orientamento LibRaw a un'immagine nell'orientamento del sensore."""
    if flip == 3:
        return arr[::-1, ::-1]
    if flip == 5:
        return np.rot90(arr, 1)
    if flip == 6:
        return np.rot90(arr, -1)
    return arr


def display_rect_to_sensor(
    rect: tuple[int, int, int, int], flip: int, sensor_w: int, sensor_h: int
) -> tuple[int, int, int, int]:
    """Converte un rettangolo (x, y, w, h) dell'immagine orientata in coordinate del sensore."""
    x, y, w, h = rect
    if flip == 3:
        return sensor_w - (x + w), sensor_h - (y + h), w, h
    if flip == 6:  # immagine = rot90 orario del sensore
        return y, sensor_h - (x + w), h, w
    if flip == 5:  # immagine = rot90 antiorario del sensore
        return sensor_w - (y + h), x, h, w
    return x, y, w, h


# ---------------------------------------------------------------- piani Bayer


class BayerLayout:
    """Posizione dei quattro piani nel pattern 2x2 e livelli di nero/bianco."""

    def __init__(self, raw: rawpy.RawPy):
        colors = raw.raw_colors_visible[:2, :2]
        desc = raw.color_desc.decode("ascii", "replace")
        blacks = np.asarray(raw.black_level_per_channel, dtype=np.float64)
        self.white = float(raw.white_level)
        offsets: dict[str, list[tuple[int, int, float]]] = {"R": [], "G": [], "B": []}
        for i in range(2):
            for j in range(2):
                offsets[desc[colors[i, j]]].append((i, j, float(blacks[colors[i, j]])))
        if len(offsets["R"]) != 1 or len(offsets["G"]) != 2 or len(offsets["B"]) != 1:
            raise ValueError("Il sensore non ha un pattern Bayer standard")
        # Ordine: R, G1, G2, B; rgb indica quale modello di rumore usare.
        self.planes = [offsets["R"][0], offsets["G"][0], offsets["G"][1], offsets["B"][0]]
        self.rgb = [0, 1, 1, 2]


def _stabilize(x: np.ndarray, a: float, b: float) -> np.ndarray:
    a = max(a, 1e-7)
    return (2.0 * np.sqrt(np.maximum(x / a + 0.375 + b / a**2, 0.0))).astype(np.float32)


def _unstabilize(d: np.ndarray, a: float, b: float) -> np.ndarray:
    a = max(a, 1e-7)
    d = np.maximum(d.astype(np.float64), 1e-3)
    z = 0.25 * d**2 + 0.25 * _SQRT_3_2 / d - 1.375 / d**2 + 0.625 * _SQRT_3_2 / d**3 - 0.125 - b / a**2
    z = np.where(d < 1.5, 0.25 * d**2 - 0.375 - b / a**2, z)
    return (np.maximum(z, 0.0) * a).astype(np.float32)


def denoise_sensor_region(
    raw: rawpy.RawPy,
    region: tuple[int, int, int, int] | None,
    model: NoiseModel,
    algorithm: Denoiser,
    settings: DenoiseSettings,
    progress: Callable[[float, str], None] | None = None,
) -> None:
    """Ripulisce in place i dati grezzi di ``raw`` nella regione (x, y, w, h) del sensore."""
    layout = BayerLayout(raw)
    visible = raw.raw_image_visible
    full_h, full_w = visible.shape
    if region is None:
        x0, y0, x1, y1 = 0, 0, full_w, full_h
    else:
        x, y, w, h = region
        pad = 2 * algorithm.margin
        x0, y0 = max(0, x - pad) & ~1, max(0, y - pad) & ~1
        x1, y1 = min(full_w, x + w + pad), min(full_h, y + h + pad)
    # Dimensioni pari, così ogni piano ha la stessa forma.
    x1 -= (x1 - x0) % 2
    y1 -= (y1 - y0) % 2
    if x1 - x0 < 4 or y1 - y0 < 4:
        return
    block = visible[y0:y1, x0:x1]

    stab = []
    norm = []
    for (i, j, black), c in zip(layout.planes, layout.rgb):
        span = max(layout.white - black, 1.0)
        plane = (block[i::2, j::2].astype(np.float32) - black) / span
        norm.append(plane)
        stab.append(_stabilize(plane, float(model.a[c]), float(model.b[c])))
    stacked = np.stack(stab, axis=-1)

    if settings.hot_pixel_threshold > 0:
        stacked = _remove_hot_pixels(stacked, settings.hot_pixel_threshold)

    if algorithm.joint:
        stacked = _joint_sensor_denoise(stacked, model, layout, algorithm, settings, progress)
    else:
        stacked = _packed_denoise(stacked, algorithm, settings, progress)

    for k, ((i, j, black), c) in enumerate(zip(layout.planes, layout.rgb)):
        span = max(layout.white - black, 1.0)
        plane = _unstabilize(stacked[..., k], float(model.a[c]), float(model.b[c]))
        block[i::2, j::2] = np.clip(np.round(plane * span + black), 0, 65535).astype(visible.dtype)


def _packed_denoise(
    stacked: np.ndarray, algorithm: Denoiser, settings: DenoiseSettings, progress: Callable[[float, str], None] | None
) -> np.ndarray:
    """Algoritmi classici: componenti ortonormali dei quattro piani, ripulite una alla volta."""
    comps = stacked @ _PACKED.T
    strengths = (settings.luma_strength, settings.chroma_strength, settings.chroma_strength, settings.chroma_strength)
    names = ("luminanza", "colore rosso-blu", "colore verde-magenta", "equilibrio dei verdi")
    for k, strength in enumerate(strengths):
        if progress is not None:
            progress(k / 4, f"Denoise sensore: {names[k]}")
        if strength <= 0:
            continue
        original = np.ascontiguousarray(comps[..., k])
        # Dopo la trasformata di Anscombe il rumore ha deviazione 1 in ogni componente.
        cleaned = algorithm.denoise(original, float(strength), settings.params)
        if k == 0 and settings.detail > 0:
            cleaned = cleaned + settings.detail * (original - cleaned)
        comps[..., k] = cleaned
    return comps @ _PACKED  # trasformazione ortonormale: l'inversa è la trasposta


def _joint_sensor_denoise(
    stacked: np.ndarray,
    model: NoiseModel,
    layout: "BayerLayout",
    algorithm: Denoiser,
    settings: DenoiseSettings,
    progress: Callable[[float, str], None] | None,
) -> np.ndarray:
    """Reti neurali: i piani diventano un'immagine RGB a metà risoluzione (verde = media dei due verdi).

    La differenza tra i due verdi (dettaglio fine e squilibrio dei verdi) viene ripulita a parte
    con la wavelet.
    """
    from .algorithms import get_algorithm
    from .joint import joint_denoise

    scale = max(float(_stabilize(np.float32(1.0), float(model.a[c]), float(model.b[c]))) for c in range(3))
    r, g1, g2, b = (stacked[..., k] for k in range(4))
    rgb = np.stack([r, (g1 + g2) / 2, b], axis=-1) / scale
    diff = (g1 - g2) / np.sqrt(2)
    # Rumore dopo la trasformata: 1 su R e B, 1/sqrt(2) sulla media dei verdi.
    per_channel = np.sqrt((1.0 + 0.5 + 1.0) / 3.0) / scale
    cleaned = joint_denoise(algorithm, rgb, np.full(3, per_channel), settings, progress) * scale
    if settings.chroma_strength > 0:
        wavelet = get_algorithm("wavelet")
        diff = wavelet.denoise(np.ascontiguousarray(diff), float(settings.chroma_strength), {})
    g = cleaned[..., 1]
    return np.stack(
        [cleaned[..., 0], g + diff / np.sqrt(2), g - diff / np.sqrt(2), cleaned[..., 2]], axis=-1
    ).astype(np.float32)


def _remove_hot_pixels(stacked: np.ndarray, threshold: float) -> np.ndarray:
    """Nel dominio stabilizzato il rumore vale 1: un pixel isolato oltre la soglia è un pixel caldo."""
    out = stacked.copy()
    for k in range(stacked.shape[-1]):
        plane = np.ascontiguousarray(stacked[..., k])
        med = cv2.medianBlur(plane, 3)
        hot = (plane - med) > threshold
        out[..., k] = np.where(hot, med, plane)
    return out


def develop_denoised(
    data: bytes,
    params: dict,
    model: NoiseModel,
    algorithm: Denoiser,
    settings: DenoiseSettings,
    sensor_region: tuple[int, int, int, int] | None = None,
    progress: Callable[[float, str], None] | None = None,
) -> np.ndarray:
    """Riapre il RAW, ripulisce i dati del sensore e lo sviluppa: RGB lineare float32 (orientamento del sensore)."""
    with rawpy.imread(io.BytesIO(data)) as raw:
        denoise_sensor_region(raw, sensor_region, model, algorithm, settings, progress)
        if progress is not None:
            progress(0.95, "Sviluppo del RAW")
        return raw.postprocess(**params).astype(np.float32) / 65535.0
