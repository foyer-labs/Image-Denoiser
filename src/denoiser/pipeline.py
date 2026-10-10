"""Pipeline di denoise (livello 2: RGB lineare dopo la demosaicizzazione di LibRaw).

Passi per un RAW:
1. (opzionale) rimozione dei pixel caldi;
2. trasformata di Anscombe generalizzata con il modello di rumore stimato dalla foto
   -> rumore uniforme;
3. separazione in luminanza e due componenti di colore;
4. denoise di ciascuna componente con forza separata per luminanza e colore;
5. ritorno in RGB lineare con l'inversa non distorta;
6. resa tonale minima (luminosità automatica + esposizione) e codifica sRGB.

Per JPG/PNG si salta la trasformata (i valori sono già codificati) e la resa tonale.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from . import vst
from .bayer import develop_denoised, display_rect_to_sensor, orient
from .algorithms import get_algorithm
from .color import opponent_to_rgb, rgb_to_opponent, srgb_encode
from .hotpixel import remove_hot_pixels
from .image import Domain, ImageData
from .joint import joint_denoise
from .noise import NoiseModel, estimate_noise_model, estimate_sigma, sample_tiles
from .settings import Settings

#: Rettangolo (x, y, larghezza, altezza) in coordinate dell'immagine.
Region = tuple[int, int, int, int]
ProgressFn = Callable[[float, str], None]

_COMPONENT_NAMES = ("luminanza", "colore 1", "colore 2")


@dataclass
class Analysis:
    """Misure fatte una volta sull'intera immagine e riusate per ogni anteprima o esportazione."""

    domain: Domain
    noise_model: NoiseModel | None
    #: Rumore per canale RGB nel dominio dei pixel (solo immagini già codificate).
    channel_sigma: np.ndarray
    #: Rumore delle componenti (luminanza, colore 1, colore 2) nel dominio di lavoro.
    component_sigma: np.ndarray
    #: Guadagno della luminosità automatica (solo RAW).
    brightness_gain: float = 1.0

    def describe(self) -> str:
        y, c1, c2 = self.component_sigma
        text = f"Rumore stimato — luminanza {y:.3g}, colore {(c1 + c2) / 2:.3g}"
        if self.noise_model is not None:
            text += " (unità stabilizzate, ~1 = rumore tipico)"
        return text


def analyze(image: ImageData, max_pixels: int = 4_000_000) -> Analysis:
    tiles = sample_tiles(image.pixels, max_pixels)
    channel_sigma = np.zeros(3)
    gain = 1.0
    if image.domain is Domain.LINEAR:
        luminance = np.concatenate([t.max(axis=2).ravel() for t in tiles])
        p99 = float(np.percentile(luminance, 99))
        gain = float(np.clip(1.0 / p99, 1.0, 16.0)) if p99 > 0 else 1.0
        if image.noise_profile is not None:
            # Misura precisa fatta durante lo sviluppo (gemello di rumore).
            model = image.noise_profile.model
            component_sigma = image.noise_profile.component_sigma.copy()
        else:
            # Ripiego (es. sensori X-Trans): stima sull'immagine sviluppata, che tende a
            # sottovalutare il rumore; la forza va alzata a mano.
            model = estimate_noise_model(image.pixels, max_pixels)
            work_tiles = [rgb_to_opponent(vst.forward(t, model)) for t in tiles]
            component_sigma = np.array([estimate_sigma([t[..., i] for t in work_tiles]) for i in range(3)])
    else:
        model = None
        work_tiles = [rgb_to_opponent(t) for t in tiles]
        channel_sigma = np.array([estimate_sigma([t[..., c] for t in tiles]) for c in range(3)])
        component_sigma = np.array([estimate_sigma([t[..., i] for t in work_tiles]) for i in range(3)])
    return Analysis(
        domain=image.domain,
        noise_model=model,
        channel_sigma=channel_sigma,
        component_sigma=component_sigma,
        brightness_gain=gain,
    )


def render(
    image: ImageData,
    analysis: Analysis,
    settings: Settings,
    region: Region | None = None,
    denoise: bool = True,
    progress: ProgressFn | None = None,
) -> np.ndarray:
    """Restituisce l'immagine (o la regione) pronta da visualizzare/salvare: sRGB float32 in [0, 1]."""
    work = denoise_region(image, analysis, settings, region, denoise, progress)
    return np.ascontiguousarray(_tone(work, image.domain, analysis, settings))


def denoise_region(
    image: ImageData,
    analysis: Analysis,
    settings: Settings,
    region: Region | None = None,
    denoise: bool = True,
    progress: ProgressFn | None = None,
) -> np.ndarray:
    """Come :func:`render` ma senza resa tonale: RGB lineare per i RAW, valori originali per JPG/PNG."""
    ds = settings.denoise
    algorithm = get_algorithm(ds.algorithm)
    x, y, w, h = region if region is not None else (0, 0, image.width, image.height)
    active = ds.luma_strength > 0 or ds.chroma_strength > 0 or ds.hot_pixel_threshold > 0
    if denoise and active and uses_sensor_stage(image, settings):
        return _render_sensor_stage(image, settings, region, progress)

    margin = algorithm.margin if denoise else 0
    px0, py0 = max(0, x - margin), max(0, y - margin)
    px1, py1 = min(image.width, x + w + margin), min(image.height, y + h + margin)
    work = image.pixels[py0:py1, px0:px1].copy()
    if denoise and active:
        work = _denoise_rgb_stage(work, analysis, settings, algorithm, progress)
    if progress is not None:
        progress(1.0, "Completato")
    return np.ascontiguousarray(work[y - py0 : y - py0 + h, x - px0 : x - px0 + w])


def _denoise_rgb_stage(
    work: np.ndarray, analysis: Analysis, settings: Settings, algorithm, progress: ProgressFn | None
) -> np.ndarray:
    """Livello 2 (RAW sviluppati) e immagini già codificate (JPG, PNG, TIFF)."""
    ds = settings.denoise
    if ds.hot_pixel_threshold > 0:
        if progress is not None:
            progress(0.0, "Pixel caldi")
        work, _ = remove_hot_pixels(work, ds.hot_pixel_threshold, _noise_std_fn(analysis))
    strengths = (ds.luma_strength, ds.chroma_strength, ds.chroma_strength)
    if not any(s > 0 for s in strengths):
        return work
    model = analysis.noise_model
    stab = vst.forward(work, model) if model is not None else work
    if algorithm.joint:
        # Le reti lavorano su valori circa in [0, 1].
        scale = vst.max_value(model) if model is not None else 1.0
        stab = joint_denoise(algorithm, stab / scale, analysis.component_sigma / scale, ds, progress) * scale
    else:
        opp = rgb_to_opponent(stab)
        for i, strength in enumerate(strengths):
            if progress is not None:
                progress(i / 3, f"Denoise {_COMPONENT_NAMES[i]}")
            if strength <= 0:
                continue
            original = opp[..., i].copy()
            cleaned = algorithm.denoise(original, float(analysis.component_sigma[i] * strength), ds.params)
            if i == 0 and ds.detail > 0:
                cleaned = cleaned + ds.detail * (original - cleaned)
            opp[..., i] = cleaned
        stab = opponent_to_rgb(opp)
    return vst.inverse(stab, model) if model is not None else stab


def uses_sensor_stage(image: ImageData, settings: Settings) -> bool:
    """True se il denoise avverrà sui dati del sensore (livello 3)."""
    return image.raw_source is not None and settings.denoise.raw_stage == "sensor"


def _render_sensor_stage(
    image: ImageData, settings: Settings, region: Region | None, progress: ProgressFn | None
) -> np.ndarray:
    """Livello 3: denoise dei dati grezzi (solo la zona richiesta) e sviluppo con LibRaw."""
    src = image.raw_source
    assert src is not None
    if src.flip in (5, 6):
        sensor_w, sensor_h = image.height, image.width
    else:
        sensor_w, sensor_h = image.width, image.height
    sensor_rect = None if region is None else display_rect_to_sensor(region, src.flip, sensor_w, sensor_h)
    algorithm = get_algorithm(settings.denoise.algorithm)
    linear = develop_denoised(
        src.data, src.params, src.sensor_model, algorithm, settings.denoise, sensor_rect, progress
    )
    oriented = orient(linear, src.flip)
    if progress is not None:
        progress(1.0, "Completato")
    if region is None:
        return np.ascontiguousarray(oriented)
    x, y, w, h = region
    return oriented[y : y + h, x : x + w].copy()


def _noise_std_fn(analysis: Analysis) -> Callable[[np.ndarray, int], np.ndarray]:
    if analysis.noise_model is not None:
        return analysis.noise_model.std_at
    sigma = analysis.channel_sigma
    return lambda level, c: np.full_like(level, max(float(sigma[c]), 1e-6))


def _tone(work: np.ndarray, domain: Domain, analysis: Analysis, settings: Settings) -> np.ndarray:
    if domain is Domain.DISPLAY:
        return np.clip(work, 0.0, 1.0).astype(np.float32)
    gain = analysis.brightness_gain if settings.tone.auto_brightness else 1.0
    gain *= 2.0 ** settings.tone.exposure_ev
    return srgb_encode(work * gain)


def process_image(
    image: ImageData,
    settings: Settings,
    analysis: Analysis | None = None,
    progress: ProgressFn | None = None,
) -> np.ndarray:
    """Elabora l'intera immagine."""
    analysis = analysis or analyze(image)
    return render(image, analysis, settings, progress=progress)
