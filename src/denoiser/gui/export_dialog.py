"""Finestra «Esporta»: dove salvare, in che formato e, per più foto, con quale metodo."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..algorithms import ALGORITHMS, get_algorithm
from ..batch import EXISTING_POLICIES
from ..image import ImageMeta
from ..io.naming import output_path
from ..settings import OUTPUT_FORMATS, OutputSettings
from .style import WARN, icon
from .widgets import form_label, hint_label, make_combo, make_form, set_combo

_NON_RAW_FORMATS = {k: v for k, v in OUTPUT_FORMATS.items() if k != "dng"}
_DEFAULT_SUBFOLDER = "denoised"


@dataclass
class ExportChoice:
    """Scelte fatte nella finestra. ``folder`` ha lo stesso significato di :attr:`OutputSettings.folder`."""

    folder: str
    format: str
    bit_depth: int
    jpeg_quality: int
    #: Formato per JPG, PNG e TIFF quando è stato scelto il DNG (che si crea solo dai RAW).
    non_raw_format: str = "tiff"
    #: Solo per più foto: cosa fare se il file esiste già (vedi :data:`EXISTING_POLICIES`).
    policy: str = "rename"
    #: Solo per più foto: metodo di riduzione del rumore.
    algorithm: str | None = None

    def apply_to(self, out: OutputSettings) -> None:
        out.folder = self.folder
        out.format = self.format
        out.bit_depth = self.bit_depth
        out.jpeg_quality = self.jpeg_quality


class ExportDialog(QDialog):
    """``raw_count``/``non_raw_count``: quante foto RAW e non RAW verranno esportate. ``algorithm``:
    metodo attuale; se indicato la finestra lo fa scegliere (esportazione di più foto)."""

    def __init__(self, parent: QWidget | None, output: OutputSettings, example: ImageMeta, raw_count: int,
                 non_raw_count: int, algorithm: str | None = None, non_raw_format: str = "tiff",
                 policy: str = "rename", start_dir: str = ""):
        super().__init__(parent)
        many = raw_count + non_raw_count > 1
        self.setWindowTitle(f"Esporta {raw_count + non_raw_count} foto" if many else "Esporta come")
        self.setMinimumWidth(560)
        self._output = replace(output)
        self._example = example
        self._raw_count, self._non_raw_count = raw_count, non_raw_count
        self._start_dir = start_dir
        v = QVBoxLayout(self)

        v.addWidget(QLabel("<b>Dove salvare</b>"))
        self.same = QRadioButton("Nella stessa cartella della foto originale")
        self.sub = QRadioButton("In una sottocartella accanto alla foto originale:")
        self.chosen = QRadioButton("In questa cartella:")
        group = QButtonGroup(self)
        for b in (self.same, self.sub, self.chosen):
            group.addButton(b)
        self.sub_name = QLineEdit()
        self.sub_name.setPlaceholderText(_DEFAULT_SUBFOLDER)
        self.sub_name.setToolTip("Nome della sottocartella, creata accanto a ogni foto se non esiste")
        self.sub_name.textEdited.connect(lambda _t: self.sub.setChecked(True))
        self.folder = QLineEdit()
        self.folder.setPlaceholderText("Scegli una cartella…")
        self.folder.textEdited.connect(lambda _t: self.chosen.setChecked(True))
        browse = QToolButton()
        browse.setIcon(icon("folder"))
        browse.setText("Sfoglia…")
        browse.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        browse.clicked.connect(self._browse)
        v.addWidget(self.same)
        row = QHBoxLayout()
        row.addWidget(self.sub)
        row.addWidget(self.sub_name, 1)
        v.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(self.chosen)
        row.addWidget(self.folder, 1)
        row.addWidget(browse)
        v.addLayout(row)
        folder = output.folder.strip()
        if not folder:
            self.same.setChecked(True)
            self.sub_name.setText(_DEFAULT_SUBFOLDER)
        elif Path(folder).is_absolute():
            self.chosen.setChecked(True)
            self.folder.setText(folder)
            self.sub_name.setText(_DEFAULT_SUBFOLDER)
        else:
            self.sub.setChecked(True)
            self.sub_name.setText(folder)

        v.addSpacing(6)
        v.addWidget(QLabel("<b>Formato</b>"))
        form = make_form()
        self.format = make_combo(OUTPUT_FORMATS, output.format)
        self.format.setToolTip(
            "TIFF: massima qualità, per continuare il ritocco. JPEG: file piccolo, per condividere. PNG: senza "
            "perdita. DNG: un RAW ripulito, da sviluppare ancora in Lightroom, darktable e simili."
        )
        dng = self.format.model().item(self.format.findData("dng"))
        if raw_count == 0:
            dng.setEnabled(False)
            dng.setToolTip("Il DNG si può creare solo da una foto RAW.")
            if output.format == "dng":
                set_combo(self.format, "tiff")
        self.format.currentIndexChanged.connect(self._update)
        form.addRow(form_label("Formato"), self.format)
        self.bits = make_combo({"16": "16 bit (per ritoccare ancora)", "8": "8 bit (stampa e web)"},
                               str(output.bit_depth))
        form.addRow(form_label("Bit per colore"), self.bits)
        self.quality = QSpinBox()
        self.quality.setRange(1, 100)
        self.quality.setValue(output.jpeg_quality)
        self.quality.setToolTip("Qualità JPEG: 90–95 = ottima. Sotto 80 compaiono blocchetti.")
        form.addRow(form_label("Qualità JPEG"), self.quality)
        self.non_raw = make_combo(_NON_RAW_FORMATS, non_raw_format)
        self.non_raw.currentIndexChanged.connect(self._update)
        self.non_raw_label = form_label("Foto non RAW")
        form.addRow(self.non_raw_label, self.non_raw)
        self.non_raw_hint = hint_label(
            f"{non_raw_count} foto (JPG, PNG o TIFF) non possono diventare DNG, che si crea solo dai RAW: "
            "scegli in che formato salvarle."
        )
        form.addRow("", self.non_raw_hint)

        self.algorithm: QComboBox | None = None
        self.policy: QComboBox | None = None
        if algorithm is not None:
            labels = {"": "Quello di ogni foto (consigliato)"}
            for key, alg in ALGORITHMS.items():
                text = f"{alg.label} — {alg.summary}"
                if not alg.is_available():
                    text += f" (da scaricare, {alg.spec.size_mb} MB)"
                labels[key] = text
            self.algorithm = make_combo(labels, algorithm, tooltips={k: a.description for k, a in ALGORITHMS.items()})
            self.algorithm.setToolTip("Ogni foto viene esportata con le sue regolazioni. Qui puoi usare per tutte lo "
                                      "stesso metodo di riduzione del rumore, con i suoi valori consigliati.")
            self.algorithm.currentIndexChanged.connect(self._update)
            form.addRow(form_label("Metodo"), self.algorithm)
            self.policy = make_combo(EXISTING_POLICIES, policy)
            form.addRow(form_label("Se il file esiste"), self.policy)
        v.addLayout(form)

        self.example_label = hint_label()
        self.example_label.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(self.example_label)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.ok = self.buttons.addButton("Esporta", QDialogButtonBox.ButtonRole.AcceptRole)
        self.ok.setObjectName("primary")
        self.ok.setDefault(True)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        v.addWidget(self.buttons)
        # Collegati solo ora: prima della fine della costruzione non tutti i controlli esistono.
        for b in (self.same, self.sub, self.chosen):
            b.toggled.connect(self._update)
        for w in (self.sub_name, self.folder):
            w.textChanged.connect(self._update)
        self._update()

    # ------------------------------------------------------------------

    def _browse(self) -> None:
        start = self.folder.text().strip() or self._start_dir or str(self._example.source.parent)
        folder = QFileDialog.getExistingDirectory(self, "Cartella in cui salvare", start)
        if folder:
            self.folder.setText(str(Path(folder)))
            self.chosen.setChecked(True)

    def _folder_value(self) -> str:
        if self.same.isChecked():
            return ""
        if self.sub.isChecked():
            return self.sub_name.text().strip() or _DEFAULT_SUBFOLDER
        return self.folder.text().strip()

    def _update(self, *_args) -> None:
        fmt = self.format.currentData()
        self.bits.setEnabled(fmt in ("tiff", "png") or (fmt == "dng" and self.non_raw.currentData() in ("tiff", "png")))
        self.quality.setEnabled(fmt == "jpeg" or (fmt == "dng" and self.non_raw.currentData() == "jpeg"))
        mixed = fmt == "dng" and self._non_raw_count > 0
        for w in (self.non_raw_label, self.non_raw, self.non_raw_hint):
            w.setVisible(mixed)
        folder = self._folder_value()
        problems = []
        if self.chosen.isChecked() and not (folder and Path(folder).is_absolute()):
            problems.append("Scegli la cartella in cui salvare (Sfoglia…).")
        if self.algorithm is not None and self.algorithm.currentData() and                 not get_algorithm(self.algorithm.currentData()).is_available():
            spec = get_algorithm(self.algorithm.currentData()).spec
            problems.append(f"{spec.label} non è ancora sul computer: alla conferma ti verrà proposto di "
                            f"scaricarlo ({spec.size_mb} MB, una sola volta).")
        out = replace(self._output, folder=folder, format=fmt)
        text = ""
        if not (self.chosen.isChecked() and not folder):
            example = output_path(self._example, out, self.algorithm.currentData() if self.algorithm else "")
            many = self._raw_count + self._non_raw_count > 1
            text = f"{'Ad esempio' if many else 'Verrà salvato come'}: {example}"
        if self.same.isChecked():
            text += ("<br>Se il formato è quello dell'originale, al nome si aggiunge «_1»: l'originale non viene "
                     "mai sovrascritto.")
        if problems:
            text += ("<br>" if text else "") + "<br>".join(f"<span style='color:{WARN}'>{p}</span>" for p in problems)
        self.example_label.setText(text)
        self.ok.setEnabled(not (self.chosen.isChecked() and not (folder and Path(folder).is_absolute())))

    def choice(self) -> ExportChoice:
        return ExportChoice(
            folder=self._folder_value(),
            format=self.format.currentData(),
            bit_depth=int(self.bits.currentData()),
            jpeg_quality=self.quality.value(),
            non_raw_format=self.non_raw.currentData(),
            policy=self.policy.currentData() if self.policy is not None else "rename",
            algorithm=(self.algorithm.currentData() or None) if self.algorithm is not None else None,
        )


__all__ = ["ExportChoice", "ExportDialog"]
