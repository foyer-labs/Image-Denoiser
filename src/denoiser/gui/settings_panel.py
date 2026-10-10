"""Pannello con tutti i parametri sempre visibili, raggruppati per sezione."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..algorithms import ALGORITHMS, get_algorithm
from ..io.naming import PLACEHOLDERS
from ..settings import DEMOSAIC_ALGORITHMS, OUTPUT_FORMATS, RAW_STAGES, WB_MODES, Settings
from .widgets import FloatControl, ParamForm, make_combo, set_combo


class SettingsPanel(QWidget):
    denoiseChanged = Signal()
    toneChanged = Signal()
    developChanged = Signal()
    outputChanged = Signal()
    dngConverterChanged = Signal(str)

    def __init__(self, settings: Settings):
        super().__init__()
        self._settings = settings
        layout = QVBoxLayout(self)

        self.info = QLabel("Nessuna foto aperta.")
        self.info.setWordWrap(True)
        info_box = QGroupBox("Foto")
        QVBoxLayout(info_box).addWidget(self.info)
        layout.addWidget(info_box)

        layout.addWidget(self._build_denoise())
        self.algo_box = QGroupBox("Parametri dell'algoritmo")
        self.algo_layout = QVBoxLayout(self.algo_box)
        self.algo_form: ParamForm | None = None
        layout.addWidget(self.algo_box)
        layout.addWidget(self._build_raw())
        layout.addWidget(self._build_output())
        layout.addStretch(1)
        self._rebuild_algorithm_form()

    # ------------------------------------------------------------------ sezioni

    def _build_denoise(self) -> QGroupBox:
        d = self._settings.denoise
        box = QGroupBox("Riduzione del rumore")
        form = QFormLayout(box)
        self.algorithm = make_combo({k: a.label for k, a in ALGORITHMS.items()}, d.algorithm)
        self.algorithm.setToolTip("\n\n".join(f"{a.label}: {a.description}" for a in ALGORITHMS.values()))
        self.algorithm.currentIndexChanged.connect(self._on_algorithm)
        form.addRow("Algoritmo", self.algorithm)

        self.raw_stage = make_combo(RAW_STAGES, d.raw_stage)
        self.raw_stage.setToolTip(
            "Livello 3: il rumore viene tolto dai dati del sensore prima della demosaicizzazione, "
            "dove è più facile da misurare e separare dal dettaglio (solo sensori Bayer).\n"
            "Livello 2: il rumore viene tolto dall'immagine già sviluppata."
        )
        self.raw_stage.currentIndexChanged.connect(self.denoiseChanged)
        form.addRow("Fase (RAW)", self.raw_stage)

        self.luma = FloatControl(0.0, 3.0, 0.05, d.luma_strength)
        self.luma.setToolTip(
            "Forza sulla luminanza (grana). 1 = rumore misurato nella foto; "
            "meno di 1 lascia un po' di grana naturale, più di 1 leviga di più."
        )
        self.luma.valueChanged.connect(self.denoiseChanged)
        form.addRow("Forza luminanza", self.luma)

        self.chroma = FloatControl(0.0, 4.0, 0.05, d.chroma_strength)
        self.chroma.setToolTip("Forza sul rumore di colore (macchie colorate). Si può spingere più della luminanza.")
        self.chroma.valueChanged.connect(self.denoiseChanged)
        form.addRow("Forza colore", self.chroma)

        self.detail = FloatControl(0.0, 1.0, 0.05, d.detail)
        self.detail.setToolTip("Reintroduce una parte della luminanza originale: recupera dettaglio e grana fine.")
        self.detail.valueChanged.connect(self.denoiseChanged)
        form.addRow("Recupero dettaglio", self.detail)

        self.hot = FloatControl(0.0, 20.0, 0.5, d.hot_pixel_threshold, decimals=1)
        self.hot.setToolTip(
            "Rimuove i pixel caldi isolati più luminosi dei vicini di questo multiplo del rumore. "
            "0 = disattivato; valori tipici 6-10."
        )
        self.hot.valueChanged.connect(self.denoiseChanged)
        form.addRow("Pixel caldi (soglia)", self.hot)
        return box

    def _build_raw(self) -> QGroupBox:
        dv, tn = self._settings.develop, self._settings.tone
        box = QGroupBox("Sviluppo RAW")
        form = QFormLayout(box)
        self.wb = make_combo(WB_MODES, dv.wb_mode)
        self.wb.setToolTip("Bilanciamento del bianco usato per sviluppare il RAW.")
        self.wb.currentIndexChanged.connect(self._on_wb)
        form.addRow("Bilanciamento bianco", self.wb)

        self.wb_spins: list[QDoubleSpinBox] = []
        row = QHBoxLayout()
        for label, value in zip("RGB", dv.wb_custom):
            spin = QDoubleSpinBox()
            spin.setRange(0.1, 8.0)
            spin.setSingleStep(0.05)
            spin.setDecimals(3)
            spin.setValue(value)
            spin.setPrefix(f"{label} ")
            spin.setKeyboardTracking(False)
            spin.valueChanged.connect(self.developChanged)
            self.wb_spins.append(spin)
            row.addWidget(spin)
        wb_row = QWidget()
        wb_row.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        wb_row.setToolTip("Moltiplicatori dei canali per il bilanciamento personalizzato.")
        form.addRow("Moltiplicatori", wb_row)

        self.demosaic = make_combo(DEMOSAIC_ALGORITHMS, dv.demosaic)
        self.demosaic.setToolTip("Algoritmo che ricostruisce i colori mancanti di ogni pixel del sensore.")
        self.demosaic.currentIndexChanged.connect(self.developChanged)
        form.addRow("Demosaicizzazione", self.demosaic)

        self.auto_bright = QCheckBox("Luminosità automatica")
        self.auto_bright.setChecked(tn.auto_brightness)
        self.auto_bright.setToolTip("Schiarisce il RAW come farebbe la fotocamera (le alte luci più forti restano intatte).")
        self.auto_bright.toggled.connect(self.toneChanged)
        form.addRow("", self.auto_bright)

        self.exposure = FloatControl(-3.0, 3.0, 0.1, tn.exposure_ev)
        self.exposure.setToolTip("Correzione di esposizione in stop (EV).")
        self.exposure.valueChanged.connect(self.toneChanged)
        form.addRow("Esposizione (EV)", self.exposure)

        self.dng_label = QLabel()
        self.dng_label.setWordWrap(True)
        dng_button = QPushButton("Scegli…")
        dng_button.setToolTip("Percorso di Adobe DNG Converter, usato per i RAW che LibRaw non supporta.")
        dng_button.clicked.connect(self._choose_dng_converter)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.dng_label, 1)
        row.addWidget(dng_button)
        dng_row = QWidget()
        dng_row.setLayout(row)
        form.addRow("DNG Converter", dng_row)
        self._update_wb_enabled()
        return box

    def _build_output(self) -> QGroupBox:
        o = self._settings.output
        box = QGroupBox("Uscita")
        form = QFormLayout(box)
        self.format = make_combo(OUTPUT_FORMATS, o.format)
        self.format.currentIndexChanged.connect(self._on_output)
        form.addRow("Formato", self.format)

        self.bits = make_combo({"16": "16 bit", "8": "8 bit"}, str(o.bit_depth))
        self.bits.setToolTip("Profondità per TIFF e PNG. 16 bit conserva le sfumature per le elaborazioni successive.")
        self.bits.currentIndexChanged.connect(self._on_output)
        form.addRow("Profondità", self.bits)

        self.quality = QSpinBox()
        self.quality.setRange(1, 100)
        self.quality.setValue(o.jpeg_quality)
        self.quality.setToolTip("Qualità JPEG (95 = alta qualità).")
        self.quality.valueChanged.connect(self._on_output)
        form.addRow("Qualità JPEG", self.quality)

        self.folder = QLineEdit(o.folder)
        self.folder.setToolTip("Cartella di destinazione: relativa alla cartella della foto (es. «denoised») oppure assoluta.")
        self.folder.editingFinished.connect(self._on_output)
        browse = QPushButton("…")
        browse.setFixedWidth(30)
        browse.clicked.connect(self._choose_folder)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.folder, 1)
        row.addWidget(browse)
        folder_row = QWidget()
        folder_row.setLayout(row)
        form.addRow("Cartella", folder_row)

        self.name = QLineEdit(o.name_template)
        self.name.setToolTip("Modello del nome. Segnaposto:\n" + "\n".join(f"{{{k}}}: {v}" for k, v in PLACEHOLDERS.items()))
        self.name.editingFinished.connect(self._on_output)
        form.addRow("Nome file", self.name)

        self.overwrite = QCheckBox("Sovrascrivi senza chiedere")
        self.overwrite.setChecked(o.overwrite)
        self.overwrite.toggled.connect(self._on_output)
        form.addRow("", self.overwrite)
        self._update_output_enabled()
        return box

    # ------------------------------------------------------------------ eventi

    def _rebuild_algorithm_form(self) -> None:
        if self.algo_form is not None:
            self.algo_layout.removeWidget(self.algo_form)
            self.algo_form.deleteLater()
        algorithm = get_algorithm(self.algorithm.currentData())
        values = self._settings.denoise.params if self._settings.denoise.algorithm == algorithm.key else {}
        self.algo_form = ParamForm(algorithm.params, algorithm.resolve(values))
        self.algo_form.changed.connect(self.denoiseChanged)
        self.algo_layout.addWidget(self.algo_form)
        self.algo_box.setTitle(f"Parametri: {algorithm.label}")
        self.algo_box.setToolTip(algorithm.description)

    def _on_algorithm(self) -> None:
        self._rebuild_algorithm_form()
        self.denoiseChanged.emit()

    def _on_wb(self) -> None:
        self._update_wb_enabled()
        self.developChanged.emit()

    def _update_wb_enabled(self) -> None:
        custom = self.wb.currentData() == "custom"
        for spin in self.wb_spins:
            spin.setEnabled(custom and self.wb.isEnabled())

    def _on_output(self) -> None:
        self._update_output_enabled()
        self.outputChanged.emit()

    def _update_output_enabled(self) -> None:
        fmt = self.format.currentData()
        self.bits.setEnabled(fmt != "jpeg")
        self.quality.setEnabled(fmt == "jpeg")

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Cartella di uscita")
        if folder:
            self.folder.setText(folder)
            self._on_output()

    def _choose_dng_converter(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Adobe DNG Converter", "", "Programmi (*.exe);;Tutti i file (*)")
        if path:
            self.dngConverterChanged.emit(path)

    # ------------------------------------------------------------------ stato

    def set_dng_converter(self, path: str | None) -> None:
        self.dng_label.setText(path if path else "Non trovato (necessario solo per i RAW non supportati)")

    def set_image_info(self, text: str, is_raw: bool, is_bayer: bool) -> None:
        self.info.setText(text)
        for w in (self.wb, self.demosaic, self.auto_bright, self.exposure):
            w.setEnabled(is_raw)
        self.raw_stage.setEnabled(is_bayer)
        self._update_wb_enabled()

    def settings(self) -> Settings:
        s = self._settings
        d = s.denoise
        d.algorithm = self.algorithm.currentData()
        d.raw_stage = self.raw_stage.currentData()
        d.params = self.algo_form.values() if self.algo_form else {}
        d.luma_strength = self.luma.value()
        d.chroma_strength = self.chroma.value()
        d.detail = self.detail.value()
        d.hot_pixel_threshold = self.hot.value()
        s.develop.wb_mode = self.wb.currentData()
        s.develop.wb_custom = tuple(spin.value() for spin in self.wb_spins)
        s.develop.demosaic = self.demosaic.currentData()
        s.tone.auto_brightness = self.auto_bright.isChecked()
        s.tone.exposure_ev = self.exposure.value()
        o = s.output
        o.format = self.format.currentData()
        o.bit_depth = int(self.bits.currentData())
        o.jpeg_quality = self.quality.value()
        o.folder = self.folder.text().strip()
        o.name_template = self.name.text().strip() or "{nome}_dn"
        o.overwrite = self.overwrite.isChecked()
        return Settings.from_dict(s.to_dict())

    def set_settings(self, settings: Settings) -> None:
        """Carica le impostazioni (es. da un preset) senza emettere un segnale per ogni controllo."""
        self._settings = Settings.from_dict(settings.to_dict())
        s = self._settings
        widgets = [self.algorithm, self.raw_stage, self.wb, self.demosaic, self.auto_bright, self.format,
                   self.bits, self.quality, self.folder, self.name, self.overwrite, *self.wb_spins]
        for w in widgets:
            w.blockSignals(True)
        set_combo(self.algorithm, s.denoise.algorithm)
        set_combo(self.raw_stage, s.denoise.raw_stage)
        self.luma.set_value(s.denoise.luma_strength)
        self.chroma.set_value(s.denoise.chroma_strength)
        self.detail.set_value(s.denoise.detail)
        self.hot.set_value(s.denoise.hot_pixel_threshold)
        set_combo(self.wb, s.develop.wb_mode)
        for spin, value in zip(self.wb_spins, s.develop.wb_custom):
            spin.setValue(value)
        set_combo(self.demosaic, s.develop.demosaic)
        self.auto_bright.setChecked(s.tone.auto_brightness)
        self.exposure.set_value(s.tone.exposure_ev)
        set_combo(self.format, s.output.format)
        set_combo(self.bits, str(s.output.bit_depth))
        self.quality.setValue(s.output.jpeg_quality)
        self.folder.setText(s.output.folder)
        self.name.setText(s.output.name_template)
        self.overwrite.setChecked(s.output.overwrite)
        for w in widgets:
            w.blockSignals(False)
        self._rebuild_algorithm_form()
        self._update_wb_enabled()
        self._update_output_enabled()
