"""Impostazioni di elaborazione, serializzabili come preset JSON."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any

#: Modalità di bilanciamento del bianco per i RAW, con etichetta italiana.
WB_MODES: dict[str, str] = {
    "camera": "Come scattato",
    "auto": "Automatico",
    "daylight": "Luce diurna",
    "custom": "Personalizzato",
}

#: Algoritmi di demosaicizzazione offerti (tutti disponibili nelle build standard di rawpy).
DEMOSAIC_ALGORITHMS: dict[str, str] = {
    "AHD": "AHD (predefinito)",
    "AAHD": "AAHD",
    "DCB": "DCB",
    "DHT": "DHT",
    "PPG": "PPG",
    "VNG": "VNG",
    "LINEAR": "Bilineare (veloce)",
}

#: Momento in cui si applica il denoise ai RAW.
RAW_STAGES: dict[str, str] = {
    "sensor": "Sul sensore, prima della demosaicizzazione (livello 3)",
    "rgb": "Sull'immagine sviluppata (livello 2)",
}

OUTPUT_FORMATS: dict[str, str] = {
    "tiff": "TIFF",
    "jpeg": "JPEG",
    "png": "PNG",
    "dng": "DNG (solo da RAW)",
}


@dataclass
class DevelopSettings:
    """Sviluppo del RAW (ignorato per JPG/PNG)."""

    wb_mode: str = "camera"
    #: Moltiplicatori R, G, B usati con wb_mode == "custom".
    wb_custom: tuple[float, float, float] = (2.0, 1.0, 1.5)
    demosaic: str = "AHD"


@dataclass
class DenoiseSettings:
    algorithm: str = "wavelet"
    #: Per i RAW: "sensor" (livello 3, solo sensori Bayer; gli altri ripiegano sul livello 2)
    #: oppure "rgb" (livello 2).
    raw_stage: str = "sensor"
    #: Parametri specifici dell'algoritmo; quelli mancanti assumono il valore predefinito.
    params: dict[str, Any] = field(default_factory=dict)
    #: Moltiplicatore della forza sulla luminanza (0 = nessun denoise). 1 corrisponde al rumore
    #: misurato: è il valore che dà la massima fedeltà, valori più bassi lasciano più grana.
    luma_strength: float = 1.0
    #: Moltiplicatore della forza sul colore.
    chroma_strength: float = 1.0
    #: Frazione di dettaglio originale (luminanza) reintrodotta, 0..1.
    detail: float = 0.0
    #: Soglia per i pixel caldi in multipli del rumore stimato (0 = disattivato).
    hot_pixel_threshold: float = 0.0


@dataclass
class ToneSettings:
    """Resa tonale minima per i RAW (i JPG/PNG non vengono toccati)."""

    auto_brightness: bool = True
    exposure_ev: float = 0.0


@dataclass
class OutputSettings:
    format: str = "tiff"
    bit_depth: int = 16
    jpeg_quality: int = 95
    #: Cartella di destinazione: relativa alla cartella della foto originale oppure assoluta.
    folder: str = "denoised"
    #: Modello del nome senza estensione. Segnaposto: {nome}, {metodo}, {iso}, {data}.
    name_template: str = "{nome}_dn"
    overwrite: bool = False


@dataclass
class Settings:
    develop: DevelopSettings = field(default_factory=DevelopSettings)
    denoise: DenoiseSettings = field(default_factory=DenoiseSettings)
    tone: ToneSettings = field(default_factory=ToneSettings)
    output: OutputSettings = field(default_factory=OutputSettings)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        """Crea le impostazioni da un dizionario, ignorando chiavi sconosciute."""

        def build(dc_type, values: dict[str, Any] | None):
            values = values or {}
            known = {f.name for f in fields(dc_type)}
            kwargs = {k: v for k, v in values.items() if k in known}
            if "wb_custom" in kwargs:
                kwargs["wb_custom"] = tuple(float(x) for x in kwargs["wb_custom"])
            return dc_type(**kwargs)

        return cls(
            develop=build(DevelopSettings, data.get("develop")),
            denoise=build(DenoiseSettings, data.get("denoise")),
            tone=build(ToneSettings, data.get("tone")),
            output=build(OutputSettings, data.get("output")),
        )
