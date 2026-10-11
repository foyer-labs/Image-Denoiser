"""Pannello delle impostazioni: tutti i parametri sempre visibili, ordinati per importanza e spiegati."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..algorithms import ALGORITHMS, get_algorithm
from ..io.naming import PLACEHOLDERS
from ..settings import DEMOSAIC_ALGORITHMS, OUTPUT_FORMATS, RAW_STAGES, WB_MODES, Settings
from .style import OK, WARN, icon
from .widgets import (
    ExplainFilter,
    FloatControl,
    ParamForm,
    form_label,
    guard_wheel,
    hint_label,
    make_combo,
    make_form,
    set_combo,
)

_EXPLAIN_DEFAULT = (
    "Passa il mouse su un controllo per leggerne qui la spiegazione. "
    "Doppio clic su un cursore: torna al valore consigliato."
)

_FORMAT_TIPS = {
    "tiff": "TIFF: massima qualità, per continuare il ritocco in altri programmi.",
    "jpeg": "JPEG: file piccolo, per condividere e stampare.",
    "png": "PNG: senza perdita di qualità, file grandi.",
    "dng": "DNG: un RAW ripulito, da sviluppare ancora in Lightroom, darktable e simili (solo da foto RAW).",
}


def _hot_threshold(decision: float) -> float:
    """«Decisione» 1..10 (più alto = più deciso) -> soglia in multipli del rumore (12..3)."""
    return round(13.0 - decision, 1)


def _hot_decision(threshold: float) -> float:
    return min(10.0, max(1.0, 13.0 - threshold))


class SettingsPanel(QWidget):
    denoiseChanged = Signal()
    toneChanged = Signal()
    developChanged = Signal()
    outputChanged = Signal()
    presetChosen = Signal(str)
    savePresetRequested = Signal()
    resetRequested = Signal()
    downloadRequested = Signal(str)
    dngConverterChosen = Signal(str)
    dngConverterReset = Signal()
    useDngConverterToggled = Signal(bool)

    def __init__(self, settings: Settings):
        super().__init__()
        self._settings = Settings.from_dict(settings.to_dict())
        self._settings.output.overwrite = False  # mai ricordato tra una sessione e l'altra
        self._params_by_algorithm: dict[str, dict] = {self._settings.denoise.algorithm: dict(self._settings.denoise.params)}
        self._ctx = {"has_image": False, "is_raw": False, "is_bayer": False, "shot_wb": None}
        self._custom_wb_touched = False

        self.explain = QLabel(_EXPLAIN_DEFAULT)
        self.explain.setObjectName("explain")
        self.explain.setWordWrap(True)
        self.explain.setMinimumHeight(64)
        self.explain.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._explain_filter = ExplainFilter(self.explain.setText)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 4, 12, 10)
        layout.addWidget(self._build_photo())
        layout.addWidget(self._build_start())
        layout.addWidget(self._build_denoise())
        self.algo_box = QGroupBox()
        self.algo_box.setObjectName("sub")
        self.algo_layout = QVBoxLayout(self.algo_box)
        self.algo_layout.setContentsMargins(0, 4, 0, 0)
        self.neural_status = QLabel()
        self.neural_status.setTextFormat(Qt.TextFormat.RichText)
        self.neural_status.setWordWrap(True)
        self.download_button = QPushButton(icon("download"), "Scarica il modello")
        self.download_button.setObjectName("primary")
        self.download_button.clicked.connect(lambda: self.downloadRequested.emit(self.algorithm.currentData()))
        self.algo_layout.addWidget(self.neural_status)
        self.algo_layout.addWidget(self.download_button)
        self.algo_hint = hint_label("I valori predefiniti vanno bene quasi sempre.")
        self.algo_layout.addWidget(self.algo_hint)
        self.algo_form: ParamForm | None = None
        reset_params = QPushButton("Ripristina i valori consigliati del metodo")
        reset_params.setObjectName("link")
        reset_params.clicked.connect(lambda: self.algo_form.reset() if self.algo_form else None)
        self._reset_params_button = reset_params
        layout.addWidget(self.algo_box)
        layout.addWidget(self._build_raw())
        layout.addWidget(self._build_output())
        layout.addStretch(1)
        self._rebuild_algorithm_form()
        self._install_explain(self)
        self.set_image_context(None)

    # ================================================================== sezioni

    def _build_photo(self) -> QWidget:
        box = QGroupBox("FOTO")
        v = QVBoxLayout(box)
        v.setSpacing(2)
        self.photo_title = QLabel("Nessuna foto aperta")
        self.photo_title.setObjectName("title")
        self.photo_details = hint_label("Apri una foto RAW, JPG, PNG o TIFF per iniziare.")
        self.photo_noise = QLabel()
        self.photo_noise.setWordWrap(True)
        self.photo_noise.setTextFormat(Qt.TextFormat.RichText)
        self.photo_notes = hint_label()
        for w in (self.photo_title, self.photo_details, self.photo_noise, self.photo_notes):
            v.addWidget(w)
        self.photo_noise.hide()
        self.photo_notes.hide()
        return box

    def _build_start(self) -> QWidget:
        box = QGroupBox("PUNTO DI PARTENZA")
        v = QVBoxLayout(box)
        self.preset = QComboBox()
        guard_wheel(self.preset)
        self.preset.setToolTip(
            "Combinazioni pronte di impostazioni. «Bilanciato» toglie esattamente il rumore misurato ed è "
            "la scelta giusta quasi sempre. Dopo averne scelto uno puoi ritoccare tutto."
        )
        self.preset.activated.connect(lambda _i: self.presetChosen.emit(self.preset.currentData() or ""))
        v.addWidget(self.preset)
        self.preset_desc = hint_label()
        v.addWidget(self.preset_desc)
        row = QHBoxLayout()
        save = QPushButton("Salva come preset…")
        save.setToolTip("Salva le impostazioni correnti con un nome, per riusarle su altre foto.")
        save.clicked.connect(self.savePresetRequested)
        reset = QPushButton(icon("reset"), "Valori consigliati")
        reset.setToolTip("Riporta tutte le regolazioni del rumore e dello sviluppo ai valori consigliati.")
        reset.clicked.connect(self.resetRequested)
        row.addWidget(save)
        row.addWidget(reset)
        v.addLayout(row)
        steps = hint_label(
            "1. Doppio clic su una zona uniforme e scura per vederla al 100%.  "
            "2. Regola «Grana» finché il rumore sparisce senza effetto plastica.  "
            "3. Regola «Macchie di colore». Tutto il resto ha già valori consigliati."
        )
        v.addWidget(steps)
        return box

    def _build_denoise(self) -> QGroupBox:
        d = self._settings.denoise
        box = QGroupBox("RIDUZIONE DEL RUMORE")
        form = make_form(box)

        self.luma = FloatControl(0.0, 3.0, 0.05, d.luma_strength, default=1.0, center=1.0,
                                 hint="1 = rumore misurato · meno = più grana · più = più liscio")
        self.luma.setToolTip(
            "Quanta grana grigia togliere. 1 = esattamente il rumore misurato in questa foto: è il punto di "
            "partenza consigliato. 0,5 ne toglie metà e lascia una grana naturale. 1,5 rende più liscio, ma "
            "capelli e tessuti possono diventare «plastica». Giudica sempre al 100%."
        )
        self.luma.valueChanged.connect(self._on_denoise_value)
        self.luma_label = form_label("Grana")
        form.addRow(self.luma_label, self.luma)

        self.chroma = FloatControl(0.0, 4.0, 0.05, d.chroma_strength, default=1.0, center=1.0,
                                   hint="Puntini rossi, verdi e blu nelle zone scure")
        self.chroma.setToolTip(
            "Quanto togliere le macchioline colorate tipiche delle zone scure. 1 = rumore misurato. Puoi "
            "salire a 1,5–2 senza perdere nitidezza: al massimo i colori dei dettagli piccolissimi si spengono un po'."
        )
        self.chroma.valueChanged.connect(self._on_denoise_value)
        self.chroma_label = form_label("Macchie di colore")
        form.addRow(self.chroma_label, self.chroma)

        self.detail = FloatControl(0.0, 1.0, 0.05, d.detail, default=0.0,
                                   hint="Riporta un po' di grana fine e nitidezza")
        self.detail.setToolTip(
            "Rimette sopra il risultato una parte della foto originale, per ridare grana fine ed evitare "
            "l'effetto cera. 0 = niente. 0,1–0,2 = leggero (utile se la foto sembra di plastica). 1 = originale."
        )
        self.detail.valueChanged.connect(self._on_denoise_value)
        form.addRow(form_label("Recupero dettaglio"), self.detail)

        hot_tip = (
            "Toglie i puntini isolati troppo luminosi (pixel «bruciati» del sensore, frequenti nelle pose lunghe "
            "e con il sensore caldo). «Decisione» più alta ne toglie di più, ma oltre 8 rischi di cancellare "
            "anche stelle o piccoli riflessi veri."
        )
        self.hot_enabled = QCheckBox("Rimuovi i pixel caldi")
        self.hot_enabled.setChecked(d.hot_pixel_threshold > 0)
        self.hot_enabled.setToolTip(hot_tip)
        self.hot_enabled.toggled.connect(self._on_denoise_value)
        form.addRow(form_label("Pixel caldi"), self.hot_enabled)
        self.hot = FloatControl(1.0, 10.0, 0.5, _hot_decision(d.hot_pixel_threshold or 8.0), decimals=1, default=5.0)
        self.hot.setToolTip(hot_tip)
        self.hot.valueChanged.connect(self._on_denoise_value)
        form.addRow(form_label("Decisione"), self.hot)

        labels = {k: f"{a.label} — {a.summary}" for k, a in ALGORITHMS.items()}
        self.algorithm = make_combo(labels, d.algorithm, tooltips={k: a.description for k, a in ALGORITHMS.items()})
        self.algorithm.setToolTip(
            "Il metodo con cui il rumore viene separato dal dettaglio. Wavelet è veloce e va bene quasi sempre; "
            "i metodi IA danno in genere la qualità più alta ma sono lenti senza scheda video."
        )
        self.algorithm.currentIndexChanged.connect(self._on_algorithm)
        form.addRow(form_label("Metodo"), self.algorithm)

        self.raw_stage = make_combo(RAW_STAGES, d.raw_stage)
        self.raw_stage.setToolTip(
            "Vale solo per i file RAW. «Prima dello sviluppo» toglie il rumore dai dati grezzi del sensore, dove "
            "si distingue meglio dai dettagli veri: di solito dà il risultato più pulito. «Dopo lo sviluppo» lavora "
            "sulla foto già a colori: provalo se vedi artefatti."
        )
        self.raw_stage.currentIndexChanged.connect(self._on_denoise_value)
        form.addRow(form_label("Quando ridurre (RAW)"), self.raw_stage)
        self.stage_hint = hint_label()
        form.addRow("", self.stage_hint)
        return box

    def _build_raw(self) -> QGroupBox:
        dv, tn = self._settings.develop, self._settings.tone
        box = QGroupBox("SVILUPPO RAW")
        self.raw_box = box
        form = make_form(box)
        self.raw_hint = hint_label()
        form.addRow(self.raw_hint)

        self.wb = make_combo(WB_MODES, dv.wb_mode)
        self.wb.setToolTip(
            "Corregge le dominanti di colore. «Come scattato» usa la scelta della fotocamera. «Automatico» la "
            "ricalcola dalla foto. «Luce diurna» è tarato sul sole di mezzogiorno. «Personalizzato» attiva i tre "
            "valori qui sotto."
        )
        self.wb.currentIndexChanged.connect(self._on_wb)
        form.addRow(form_label("Bilanciamento bianco"), self.wb)

        self.wb_spins: list[QDoubleSpinBox] = []
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        for label, value in zip("RGB", dv.wb_custom):
            spin = QDoubleSpinBox()
            spin.setRange(0.1, 8.0)
            spin.setSingleStep(0.05)
            spin.setDecimals(2)
            spin.setValue(value)
            spin.setPrefix(f"{label} ")
            spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            spin.setKeyboardTracking(False)
            guard_wheel(spin)
            spin.valueChanged.connect(self._on_wb_values)
            self.wb_spins.append(spin)
            row.addWidget(spin)
        wb_row = QWidget()
        wb_row.setLayout(row)
        wb_row.setToolTip(
            "Quanto amplificare rosso, verde e blu (solo con «Personalizzato»). Alzare R scalda la foto, alzare B "
            "la raffredda; G di solito resta 1. Partono dai valori dello scatto."
        )
        form.addRow(form_label("Valori R / G / B"), wb_row)

        self.demosaic = make_combo(DEMOSAIC_ALGORITHMS, dv.demosaic)
        self.demosaic.setToolTip(
            "Il sensore registra un solo colore per pixel: questo passaggio ricostruisce gli altri due. Le "
            "differenze si vedono solo al 100% sui dettagli finissimi: AHD va bene quasi sempre."
        )
        self.demosaic.currentIndexChanged.connect(self.developChanged)
        form.addRow(form_label("Ricostruzione colori"), self.demosaic)

        self.auto_bright = QCheckBox("Luminosità automatica")
        self.auto_bright.setChecked(tn.auto_brightness)
        self.auto_bright.setToolTip("Schiarisce il RAW come farebbe la fotocamera (le alte luci più forti restano intatte).")
        self.auto_bright.toggled.connect(self.toneChanged)
        form.addRow(form_label(""), self.auto_bright)

        self.exposure = FloatControl(-3.0, 3.0, 0.1, tn.exposure_ev, default=0.0, center=0.0, suffix=" EV")
        self.exposure.setToolTip(
            "Schiarisce (+) o scurisce (−) in stop: +1 = doppio della luce, −1 = metà. Schiarire rende anche il "
            "rumore più visibile."
        )
        self.exposure.valueChanged.connect(self.toneChanged)
        form.addRow(form_label("Esposizione"), self.exposure)

        dng_tip = (
            "Programma gratuito di Adobe: serve solo per i RAW che questa app non sa ancora leggere (fotocamere "
            "appena uscite o NEF «alta efficienza»). Se è installato, il file viene convertito in DNG e aperto."
        )
        self.use_dng = QCheckBox("Usalo se un RAW non si apre")
        self.use_dng.setChecked(True)
        self.use_dng.setToolTip(dng_tip)
        self.use_dng.toggled.connect(self.useDngConverterToggled)
        form.addRow(form_label("DNG Converter"), self.use_dng)
        self.dng_label = hint_label()
        self.dng_label.setToolTip(dng_tip)
        choose = QPushButton("Scegli…")
        choose.setToolTip("Indica dove si trova «Adobe DNG Converter.exe», se non viene trovato da solo.")
        choose.clicked.connect(self._choose_dng_converter)
        clear = QPushButton("Ripristina")
        clear.setToolTip("Dimentica il percorso scelto e torna alla ricerca automatica.")
        clear.clicked.connect(self.dngConverterReset)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.dng_label, 1)
        row.addWidget(choose)
        row.addWidget(clear)
        dng_row = QWidget()
        dng_row.setLayout(row)
        form.addRow(form_label(""), dng_row)
        return box

    def _build_output(self) -> QGroupBox:
        o = self._settings.output
        box = QGroupBox("SALVATAGGIO")
        form = make_form(box)
        self.format = make_combo(OUTPUT_FORMATS, o.format, tooltips=_FORMAT_TIPS)
        self.format.setToolTip("\n".join(_FORMAT_TIPS.values()))
        self.format.currentIndexChanged.connect(self._on_output)
        form.addRow(form_label("Formato"), self.format)

        self.bits = make_combo({"16": "16 bit (per ritoccare ancora)", "8": "8 bit (stampa e web)"}, str(o.bit_depth))
        self.bits.setToolTip(
            "16 bit conserva le sfumature se ritoccherai ancora la foto (file più grandi). 8 bit basta per "
            "stampa e web. Vale per TIFF e PNG."
        )
        self.bits.currentIndexChanged.connect(self._on_output)
        form.addRow(form_label("Bit per colore"), self.bits)

        self.quality = FloatControl(1, 100, 1, o.jpeg_quality, decimals=0, default=95)
        self.quality.setToolTip("Qualità JPEG: 90–95 = ottima. Sotto 80 compaiono blocchetti.")
        self.quality.valueChanged.connect(self._on_output)
        form.addRow(form_label("Qualità JPEG"), self.quality)

        self.folder = QLineEdit(o.folder)
        self.folder.setToolTip(
            "Cartella di destinazione: un nome semplice (es. «denoised») crea una sottocartella accanto alla foto; "
            "un percorso completo salva sempre lì."
        )
        self.folder.editingFinished.connect(self._on_output)
        browse = QToolButton()
        browse.setIcon(icon("folder"))
        browse.setToolTip("Scegli la cartella")
        browse.clicked.connect(self._choose_folder)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.folder, 1)
        row.addWidget(browse)
        folder_row = QWidget()
        folder_row.setLayout(row)
        form.addRow(form_label("Cartella"), folder_row)

        self.name = QLineEdit(o.name_template)
        self.name.setToolTip(
            "Modello del nome del file. Segnaposto:\n" + "\n".join(f"{{{k}}}: {v}" for k, v in PLACEHOLDERS.items())
        )
        self.name.editingFinished.connect(self._on_output)
        insert = QToolButton()
        insert.setText("{…}")
        insert.setToolTip("Inserisci un segnaposto nel nome")
        insert.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(insert)
        for key, desc in PLACEHOLDERS.items():
            act = QAction(f"{{{key}}} — {desc}", menu)
            act.triggered.connect(lambda _c=False, k=key: self._insert_placeholder(k))
            menu.addAction(act)
        insert.setMenu(menu)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.name, 1)
        row.addWidget(insert)
        name_row = QWidget()
        name_row.setLayout(row)
        form.addRow(form_label("Nome del file"), name_row)
        self.example = hint_label()
        form.addRow("", self.example)

        self.overwrite = QCheckBox("Sovrascrivi senza chiedere")
        self.overwrite.setChecked(False)
        self.overwrite.setToolTip(
            "Se il file esiste già viene sostituito senza conferma. Per sicurezza questa scelta non viene "
            "ricordata alla prossima apertura dell'app."
        )
        self.overwrite.toggled.connect(self._on_output)
        form.addRow("", self.overwrite)

        self.copy_metadata = QCheckBox("Copia i metadati dell'originale")
        self.copy_metadata.setChecked(o.copy_metadata)
        self.copy_metadata.toggled.connect(self._on_output)
        form.addRow(form_label("Metadati"), self.copy_metadata)
        self.output_hint = hint_label()
        form.addRow("", self.output_hint)
        from ..io.metadata import find_exiftool

        tool = find_exiftool()
        self.copy_metadata.setToolTip(
            "Data, fotocamera, obiettivo, esposizione, GPS, parole chiave… copiati nel file salvato. "
            + ("Si usa ExifTool." if tool else "ExifTool non trovato: vengono copiati solo i dati essenziali dei JPG.")
        )
        return box

    # ================================================================== eventi

    def _install_explain(self, root: QWidget) -> None:
        for w in root.findChildren(QWidget):
            w.installEventFilter(self._explain_filter)

    def _on_denoise_value(self, *_args) -> None:
        self._update_applicability()
        self.denoiseChanged.emit()

    def _rebuild_algorithm_form(self) -> None:
        if self.algo_form is not None:
            self.algo_layout.removeWidget(self.algo_form)
            self.algo_form.deleteLater()
        algorithm = get_algorithm(self.algorithm.currentData())
        values = self._params_by_algorithm.get(algorithm.key, {})
        self.algo_form = ParamForm(algorithm.params, algorithm.resolve(values))
        self.algo_form.changed.connect(self._on_params)
        self.algo_layout.removeWidget(self._reset_params_button)
        self.algo_layout.addWidget(self.algo_form)
        self.algo_layout.addWidget(self._reset_params_button)
        self.algo_form.install_filter(self._explain_filter)
        self.algo_box.setTitle(f"Regolazioni avanzate · {algorithm.label}")
        self.algo_box.setToolTip(algorithm.description)
        self.refresh_algorithms()

    def _on_params(self) -> None:
        self._params_by_algorithm[self.algorithm.currentData()] = self.algo_form.values() if self.algo_form else {}
        self.denoiseChanged.emit()

    def _on_algorithm(self) -> None:
        self._rebuild_algorithm_form()
        self._update_applicability()
        self.denoiseChanged.emit()

    def _on_wb(self) -> None:
        if self.wb.currentData() == "custom" and not self._custom_wb_touched and self._ctx["shot_wb"]:
            # I valori personalizzati partono da quelli dello scatto: nessun salto di colore.
            for spin, value in zip(self.wb_spins, self._ctx["shot_wb"]):
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)
        self._update_applicability()
        self.developChanged.emit()

    def _on_wb_values(self) -> None:
        self._custom_wb_touched = True
        self.developChanged.emit()

    def _on_output(self, *_args) -> None:
        self._update_applicability()
        self.outputChanged.emit()

    def _insert_placeholder(self, key: str) -> None:
        self.name.insert("{" + key + "}")
        self._on_output()

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Cartella di uscita")
        if folder:
            self.folder.setText(folder)
            self._on_output()

    def _choose_dng_converter(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Adobe DNG Converter", "", "Programmi (*.exe);;Tutti i file (*)")
        if path:
            self.dngConverterChosen.emit(path)

    # ================================================================== applicabilità

    def _update_applicability(self) -> None:
        ctx = self._ctx
        is_raw, is_bayer = ctx["is_raw"], ctx["is_bayer"]
        fmt = self.format.currentData()
        algorithm = get_algorithm(self.algorithm.currentData())

        # Reti «cieche»: la forza è una miscela con l'originale, oltre 1 non ha effetto.
        blind = algorithm.blind
        self.luma.set_maximum(1.0 if blind else 3.0)
        self.chroma.set_maximum(1.0 if blind else 4.0)
        self.luma_label.setText("Grana (quanto applicare)" if blind else "Grana")
        self.chroma_label.setText("Colore (quanto applicare)" if blind else "Macchie di colore")
        self.luma.set_hint("1 = risultato completo · 0 = foto originale" if blind else
                           "1 = rumore misurato · meno = più grana · più = più liscio")
        self.detail.setEnabled(self.luma.value() > 0)
        self.hot.setEnabled(self.hot_enabled.isChecked())

        stage_ok = is_raw and is_bayer
        self.raw_stage.setEnabled(stage_ok)
        if not ctx["has_image"]:
            self.stage_hint.setText("")
        elif not is_raw:
            self.stage_hint.setText("Non applicabile: la foto non è un RAW.")
        elif not is_bayer:
            self.stage_hint.setText("Questo sensore (es. Fujifilm X-Trans) usa sempre «Dopo lo sviluppo».")
        else:
            self.stage_hint.setText("")
        self.stage_hint.setVisible(bool(self.stage_hint.text()))

        # Sviluppo RAW
        dng_sensor = fmt == "dng" and stage_ok and self.raw_stage.currentData() == "sensor"
        raw_controls = (self.wb, self.demosaic, self.auto_bright, self.exposure)
        for w in raw_controls:
            w.setEnabled(is_raw)
        custom = self.wb.currentData() == "custom"
        for spin in self.wb_spins:
            spin.setEnabled(is_raw and custom and not dng_sensor)
        reason = ""
        if not ctx["has_image"]:
            reason = "Apri una foto RAW per usare queste impostazioni."
        elif not is_raw:
            reason = "Non applicabile: la foto non è un RAW."
        elif dng_sensor:
            self.wb.setEnabled(False)
            self.demosaic.setEnabled(False)
            self.auto_bright.setEnabled(False)
            reason = ("Con l'uscita DNG bilanciamento, ricostruzione dei colori e luminosità si scelgono nel "
                      "programma di sviluppo: qui vengono ignorati.")
        elif fmt == "dng":
            self.auto_bright.setEnabled(False)
            reason = "Con l'uscita DNG la luminosità automatica si regola nel programma di sviluppo."
        self.raw_hint.setText(reason)
        self.raw_hint.setVisible(bool(reason))

        # Salvataggio
        self.bits.setEnabled(fmt in ("tiff", "png"))
        self.quality.setEnabled(fmt == "jpeg")
        model = self.format.model()
        dng_index = self.format.findData("dng")
        item = model.item(dng_index) if hasattr(model, "item") else None
        if item is not None:
            item.setEnabled(not ctx["has_image"] or is_raw)
        if fmt == "dng":
            kind = ("a mosaico, con i dati del sensore ripuliti" if dng_sensor
                    else "lineare, con il bilanciamento del bianco già applicato")
            self.output_hint.setText(f"DNG {kind}.")
        else:
            self.output_hint.setText("")
        self.output_hint.setVisible(bool(self.output_hint.text()))

    # ================================================================== stato dall'esterno

    def set_image_context(self, info: dict | None) -> None:
        """Aggiorna il riquadro «Foto» e l'applicabilità dei controlli.

        ``info``: title, details, noise (HTML), notes, is_raw, is_bayer, shot_wb.
        """
        if info is None:
            self._ctx = {"has_image": False, "is_raw": False, "is_bayer": False, "shot_wb": None}
            self.photo_title.setText("Nessuna foto aperta")
            self.photo_details.setText("Apri una foto RAW, JPG, PNG o TIFF per iniziare.")
            self.photo_noise.hide()
            self.photo_notes.hide()
        else:
            self._ctx = {"has_image": True, "is_raw": info["is_raw"], "is_bayer": info["is_bayer"],
                         "shot_wb": info.get("shot_wb")}
            self.photo_title.setText(info["title"])
            self.photo_details.setText(info["details"])
            self.photo_noise.setText(info.get("noise", ""))
            self.photo_noise.setVisible(bool(info.get("noise")))
            self.photo_notes.setText(info.get("notes", ""))
            self.photo_notes.setVisible(bool(info.get("notes")))
        self._update_applicability()

    def set_presets(self, entries: list[tuple[str, str]]) -> None:
        """``entries``: (nome, descrizione)."""
        self.preset.blockSignals(True)
        self.preset.clear()
        self.preset.addItem("Personalizzato", "")
        for name, desc in entries:
            self.preset.addItem(name, name)
            self.preset.setItemData(self.preset.count() - 1, desc, Qt.ItemDataRole.ToolTipRole)
        self.preset.blockSignals(False)

    def show_preset(self, name: str, description: str, modified: bool) -> None:
        index = self.preset.findData(name) if name else 0
        self.preset.blockSignals(True)
        self.preset.setCurrentIndex(max(0, index))
        if name and index >= 0:
            self.preset.setItemText(index, f"{name} (modificato)" if modified else name)
        for i in range(1, self.preset.count()):
            if i != index:
                self.preset.setItemText(i, self.preset.itemData(i))
        self.preset.blockSignals(False)
        self.preset_desc.setText(description)
        self.preset_desc.setVisible(bool(description))

    def set_dng_converter(self, path: str | None, enabled: bool) -> None:
        self.use_dng.blockSignals(True)
        self.use_dng.setChecked(enabled)
        self.use_dng.blockSignals(False)
        self.dng_label.setText(path if path else "Non installato: serve solo se un RAW non si apre.")

    def set_output_example(self, text: str) -> None:
        self.example.setText(text)

    def current_algorithm(self):
        return get_algorithm(self.algorithm.currentData())

    def refresh_algorithms(self, download_text: str | None = None) -> None:
        """Aggiorna lo stato dei modelli neurali (dopo un download, o durante)."""
        for i in range(self.algorithm.count()):
            alg = get_algorithm(self.algorithm.itemData(i))
            text = f"{alg.label} — {alg.summary}"
            if not alg.is_available():
                text += f" (da scaricare, {alg.spec.size_mb} MB)"
            self.algorithm.setItemText(i, text)
        algorithm = self.current_algorithm()
        if not algorithm.joint:
            self.neural_status.hide()
            self.download_button.hide()
            self.algo_hint.setText("I valori predefiniti vanno bene quasi sempre.")
            return
        from ..neural.runtime import gpu_status

        spec = algorithm.spec
        has_gpu, device_text = gpu_status()
        if algorithm.is_available():
            model_chip = f"<span style='color:{OK}'>● Modello pronto</span>"
        else:
            model_chip = f"<span style='color:{WARN}'>↓ Da scaricare ({spec.size_mb} MB, una sola volta)</span>"
        device_chip = (f"<span style='color:{OK}'>● {device_text}</span>" if has_gpu
                       else f"<span style='color:{WARN}'>▲ {device_text}</span>")
        self.neural_status.setText(f"{model_chip} &nbsp; {device_chip}")
        self.neural_status.setToolTip(f"{algorithm.description}\n\nLicenza del modello: {spec.license}.")
        self.neural_status.show()
        if download_text is not None:
            self.download_button.setText(download_text)
            self.download_button.setEnabled(False)
            self.download_button.show()
        elif algorithm.is_available():
            self.download_button.hide()
        else:
            self.download_button.setText(f"Scarica {spec.label} ({spec.size_mb} MB)")
            self.download_button.setEnabled(True)
            self.download_button.show()
        self.algo_hint.setText(algorithm.description)

    # ================================================================== lettura e scrittura

    def settings(self) -> Settings:
        s = self._settings
        d = s.denoise
        d.algorithm = self.algorithm.currentData()
        d.raw_stage = self.raw_stage.currentData()
        d.params = self.algo_form.values() if self.algo_form else {}
        d.luma_strength = self.luma.value()
        d.chroma_strength = self.chroma.value()
        d.detail = self.detail.value()
        d.hot_pixel_threshold = _hot_threshold(self.hot.value()) if self.hot_enabled.isChecked() else 0.0
        s.develop.wb_mode = self.wb.currentData()
        s.develop.wb_custom = tuple(spin.value() for spin in self.wb_spins)
        s.develop.demosaic = self.demosaic.currentData()
        s.tone.auto_brightness = self.auto_bright.isChecked()
        s.tone.exposure_ev = self.exposure.value()
        o = s.output
        o.format = self.format.currentData()
        o.bit_depth = int(self.bits.currentData())
        o.jpeg_quality = int(round(self.quality.value()))
        o.folder = self.folder.text().strip()
        o.name_template = self.name.text().strip() or "{nome}_dn"
        o.overwrite = self.overwrite.isChecked()
        o.copy_metadata = self.copy_metadata.isChecked()
        return Settings.from_dict(s.to_dict())

    def set_settings(self, settings: Settings) -> None:
        """Carica le impostazioni (preset, annulla/ripeti) senza emettere un segnale per ogni controllo."""
        self._settings = Settings.from_dict(settings.to_dict())
        s = self._settings
        self._params_by_algorithm[s.denoise.algorithm] = dict(s.denoise.params)
        widgets = [self.algorithm, self.raw_stage, self.wb, self.demosaic, self.auto_bright, self.format,
                   self.bits, self.folder, self.name, self.overwrite, self.copy_metadata, self.hot_enabled,
                   *self.wb_spins]
        for w in widgets:
            w.blockSignals(True)
        try:
            set_combo(self.algorithm, s.denoise.algorithm)
            set_combo(self.raw_stage, s.denoise.raw_stage)
            self.luma.set_value(s.denoise.luma_strength)
            self.chroma.set_value(s.denoise.chroma_strength)
            self.detail.set_value(s.denoise.detail)
            self.hot_enabled.setChecked(s.denoise.hot_pixel_threshold > 0)
            if s.denoise.hot_pixel_threshold > 0:
                self.hot.set_value(_hot_decision(s.denoise.hot_pixel_threshold))
            set_combo(self.wb, s.develop.wb_mode)
            for spin, value in zip(self.wb_spins, s.develop.wb_custom):
                spin.setValue(value)
            set_combo(self.demosaic, s.develop.demosaic)
            self.auto_bright.setChecked(s.tone.auto_brightness)
            self.exposure.set_value(s.tone.exposure_ev)
            set_combo(self.format, s.output.format)
            set_combo(self.bits, str(s.output.bit_depth))
            self.quality.set_value(s.output.jpeg_quality)
            self.folder.setText(s.output.folder)
            self.name.setText(s.output.name_template)
            self.overwrite.setChecked(s.output.overwrite)
            self.copy_metadata.setChecked(s.output.copy_metadata)
        finally:  # i segnali non devono restare bloccati anche se un valore non è valido
            for w in widgets:
                w.blockSignals(False)
        self._rebuild_algorithm_form()
        self._update_applicability()
