"""Sviluppo dei RAW con LibRaw (tramite rawpy) in RGB lineare a 16 bit."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import rawpy

from ..bayer import orient
from ..image import Domain, ImageData, ImageMeta, RawSource
from ..settings import DevelopSettings
from ..raw_noise import measure_noise_twin
from .exif import read_basic_exif

# Errori di LibRaw che indicano un file/fotocamera non gestibile (non un errore di I/O).
_UNSUPPORTED_ERRORS = (
    rawpy.LibRawFileUnsupportedError,
    rawpy.LibRawDataError,
    rawpy.LibRawNotImplementedError,
    rawpy.LibRawUnspecifiedError,
    rawpy.LibRawFatalError,
)


class RawDamagedError(Exception):
    """Il file RAW è vuoto o troncato: convertirlo non servirebbe."""


class RawNotSupportedError(Exception):
    """LibRaw non riesce a sviluppare correttamente questo RAW."""


def _cfa_pattern(raw: rawpy.RawPy) -> str | None:
    """Pattern Bayer 2x2 (es. "RGGB"), oppure None per X-Trans, Foveon e altri sensori."""
    pattern = raw.raw_pattern
    if pattern is None or pattern.shape != (2, 2) or raw.num_colors != 3:
        return None
    desc = raw.color_desc.decode("ascii", "replace")
    letters = "".join(desc[i] for i in pattern.ravel())
    return letters if sorted(letters) == ["B", "G", "G", "R"] else None


def _has_color_matrix(raw: rawpy.RawPy) -> bool:
    xyz = np.asarray(raw.rgb_xyz_matrix)[:3]
    cam = np.asarray(raw.color_matrix)[:3, :3]
    return bool(np.any(xyz != 0) or (np.any(cam != 0) and not np.allclose(cam, np.eye(3))))


def decode_raw(path: Path, develop: DevelopSettings | None = None, measure_noise: bool = True) -> ImageData:
    """Sviluppa il RAW in RGB lineare.

    Con ``measure_noise`` (solo sensori Bayer) misura anche il rumore con il "gemello di
    rumore": un secondo sviluppo che circa raddoppia il tempo di apertura ma rende la stima
    del rumore molto più precisa.
    """
    develop = develop or DevelopSettings()
    # Si legge il file in memoria: evita problemi con percorsi non ASCII su Windows.
    data = path.read_bytes()
    is_dng = path.suffix.lower() == ".dng"
    if not data:
        raise RawDamagedError(f"{path.name} è vuoto (0 byte).")
    try:
        raw = rawpy.imread(io.BytesIO(data))
    except _UNSUPPORTED_ERRORS as exc:
        raise RawNotSupportedError(f"LibRaw non riconosce il file ({exc.__class__.__name__}).") from exc

    with raw:
        # Va letto prima dello sviluppo: con user_flip=0 LibRaw lo azzera.
        flip = int(raw.sizes.flip)
        if not is_dng and not _has_color_matrix(raw):
            raise RawNotSupportedError(
                "LibRaw non conosce i colori di questa fotocamera (matrice colore assente): "
                "probabilmente è un modello troppo recente."
            )
        params = dict(
            gamma=(1, 1),
            no_auto_bright=True,
            output_bps=16,
            output_color=rawpy.ColorSpace.sRGB,
            demosaic_algorithm=getattr(rawpy.DemosaicAlgorithm, develop.demosaic, rawpy.DemosaicAlgorithm.AHD),
            highlight_mode=rawpy.HighlightMode.Clip,
            # Livello di bianco fisso: altrimenti LibRaw lo adatta al massimo dei dati e
            # la luminosità cambierebbe dopo il denoise dei dati grezzi.
            adjust_maximum_thr=0.0,
            # La rotazione viene applicata dopo: serve conoscere la corrispondenza tra
            # pixel dell'immagine e pixel del sensore per il denoise di livello 3.
            user_flip=0,
        )
        cam_wb = np.asarray(raw.camera_whitebalance[:3], dtype=float)
        if develop.wb_mode == "camera":
            params["use_camera_wb"] = True
            wb = cam_wb
        elif develop.wb_mode == "auto":
            params["use_auto_wb"] = True
            wb = None
        elif develop.wb_mode == "custom":
            r, g, b = develop.wb_custom
            params["user_wb"] = [float(r), float(g), float(b), float(g)]
            wb = np.array([r, g, b], dtype=float)
        else:  # luce diurna: moltiplicatori derivati dalla matrice colore
            wb = np.asarray(raw.daylight_whitebalance[:3], dtype=float)

        def develop_linear() -> np.ndarray:
            return raw.postprocess(**params).astype(np.float32) / 65535.0

        try:
            pixels = develop_linear()
        except _UNSUPPORTED_ERRORS as exc:
            raise RawNotSupportedError(f"LibRaw non riesce a sviluppare il file ({exc.__class__.__name__}).") from exc
        cfa = _cfa_pattern(raw)
        sensor_shape = raw.raw_image_visible.shape
        profile = None
        if cfa is not None and measure_noise:
            # Ultimo passo: modifica i dati grezzi di `raw`, che non vengono più usati.
            profile = measure_noise_twin(raw, develop_linear, pixels, demosaic=develop.demosaic)

    raw_source = None
    # Il livello 3 richiede che ogni pixel sviluppato corrisponda a un pixel del sensore.
    if profile is not None and profile.sensor_model is not None and pixels.shape[:2] == sensor_shape:
        raw_source = RawSource(data=data, params=params, flip=flip, sensor_model=profile.sensor_model)
    pixels = np.ascontiguousarray(orient(pixels, flip))

    if wb is not None and wb[1] > 0:
        wb_tuple = tuple(float(x) for x in wb / wb[1])
    else:
        wb_tuple = None
    exif = read_basic_exif(path)
    meta = ImageMeta(
        source=path,
        kind="raw",
        camera=exif.camera,
        make=exif.make,
        model=exif.model,
        iso=exif.iso,
        date=exif.date,
        bits_per_sample=16,
        wb_multipliers=wb_tuple,
        cfa_pattern=cfa,
    )
    return ImageData(
        pixels=pixels, domain=Domain.LINEAR, meta=meta, noise_profile=profile, raw_source=raw_source
    )
