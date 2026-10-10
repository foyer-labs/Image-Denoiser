"""Immagini di prova sintetiche con rumore noto."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from skimage import data

from denoiser.color import srgb_decode

# Matrice XYZ (D65) -> sRGB lineare: con questa ColorMatrix1 la "fotocamera" sintetica
# registra direttamente sRGB lineare, quindi lo sviluppo deve restituire l'immagine pulita.
_XYZ_TO_SRGB = [
    [3.2406, -1.5372, -0.4986],
    [-0.9689, 1.8758, 0.0415],
    [0.0557, -0.2040, 1.0570],
]


def clean_display(size: int | None = None) -> np.ndarray:
    img = (data.astronaut() / 255.0).astype(np.float32)
    return img[:size, :size] if size else img


def clean_linear(size: int | None = None, scale: float = 0.6) -> np.ndarray:
    return srgb_decode(clean_display(size)) * scale


def poisson_gaussian(linear: np.ndarray, a: float, b: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    noisy = rng.poisson(np.maximum(linear, 0) / a) * a + rng.normal(0, np.sqrt(b), linear.shape)
    return noisy.astype(np.float32)


def write_bayer_dng(
    path: Path,
    linear: np.ndarray,
    a: float = 0.0,
    b: float = 0.0,
    black: int = 256,
    white: int = 4095,
    seed: int = 0,
) -> Path:
    """Scrive un DNG Bayer RGGB a partire da un'immagine lineare, con rumore Poisson-gaussiano opzionale."""
    from pidng.core import RAW2DNG, DNGTags, Tag
    from pidng.defs import (
        CalibrationIlluminant, CFAPattern, DNGVersion, Orientation, PhotometricInterpretation,
        PreviewColorSpace,
    )

    h, w = linear.shape[:2]
    h, w = h - h % 2, w - w % 2
    mosaic = np.empty((h, w), dtype=np.float32)
    mosaic[0::2, 0::2] = linear[0:h:2, 0:w:2, 0]
    mosaic[0::2, 1::2] = linear[0:h:2, 1:w:2, 1]
    mosaic[1::2, 0::2] = linear[1:h:2, 0:w:2, 1]
    mosaic[1::2, 1::2] = linear[1:h:2, 1:w:2, 2]
    if a > 0 or b > 0:
        mosaic = poisson_gaussian(mosaic, max(a, 1e-9), b, seed)
    span = white - black
    dn = np.clip(np.round(mosaic * span + black), 0, white).astype(np.uint16)

    t = DNGTags()
    t.set(Tag.ImageWidth, w)
    t.set(Tag.ImageLength, h)
    t.set(Tag.TileWidth, w)
    t.set(Tag.TileLength, h)
    t.set(Tag.Orientation, Orientation.Horizontal)
    t.set(Tag.PhotometricInterpretation, PhotometricInterpretation.Color_Filter_Array)
    t.set(Tag.SamplesPerPixel, 1)
    t.set(Tag.BitsPerSample, 16)
    t.set(Tag.CFARepeatPatternDim, [2, 2])
    t.set(Tag.CFAPattern, CFAPattern.RGGB)
    t.set(Tag.BlackLevel, black)
    t.set(Tag.WhiteLevel, white)
    t.set(Tag.ColorMatrix1, [[int(round(v * 10000)), 10000] for row in _XYZ_TO_SRGB for v in row])
    t.set(Tag.CalibrationIlluminant1, CalibrationIlluminant.D65)
    t.set(Tag.AsShotNeutral, [[1, 1], [1, 1], [1, 1]])
    t.set(Tag.Make, "Sintetica")
    t.set(Tag.Model, "Sintetica Bayer")
    t.set(Tag.DNGVersion, DNGVersion.V1_4)
    t.set(Tag.DNGBackwardVersion, DNGVersion.V1_2)
    t.set(Tag.PreviewColorSpace, PreviewColorSpace.sRGB)

    path = Path(path)
    converter = RAW2DNG()
    converter.options(t, path=str(path.parent), compress=False)
    converter.convert(dn, filename=path.stem)
    return path.with_suffix(".dng")
