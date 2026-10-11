"""Finestra «Elabora più file»: scelta di file e cartelle, avanzamento, annullamento e riepilogo."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from ..algorithms import get_algorithm
from ..batch import collect_inputs, export_image
from ..io import load_image
from ..io.formats import file_dialog_filter, is_supported
from ..io.naming import output_path, unique_path
from ..pipeline import analyze
from ..presets import PresetError, apply_preset, list_presets, preset_content
from ..settings import Settings
from .widgets import hint_label
from .workers import EtaEstimator, Task, format_duration, start

POLICIES = {"rename": "Salva con un altro nome (_1, _2…)", "overwrite": "Sovrascrivi", "skip": "Salta la foto"}


def process_one(path: Path, settings: Settings, policy: str, converter, use_converter: bool, progress=None,
                taken: frozenset[Path] = frozenset()) -> tuple[str, Path | None, list[str]]:
    """Elabora una foto. Restituisce (esito, file salvato, note); esito: "ok" o "saltata".

    ``taken``: file già prodotti in questo stesso batch (es. IMG_1.NEF e IMG_1.JPG danno lo stesso
    nome): non vengono mai sovrascritti né fanno saltare la foto, si usa un nome nuovo.
    """
    image = load_image(path, settings.develop, use_converter, converter)
    destination = output_path(image.meta, settings.output, settings.denoise.algorithm)
    if destination in taken:
        destination = unique_path(destination)
    elif destination.exists():
        if policy == "skip":
            return "saltata", destination, []
        if policy == "rename":
            destination = unique_path(destination)
    notes = list(image.meta.notes)
    analysis = analyze(image)
    saved = export_image(image, analysis, settings, destination, progress, notes)
    return "ok", saved, notes


class BatchDialog(QDialog):
    def __init__(self, parent, current_settings: Callable[[], Settings], converter, use_converter: bool,
                 start_dir: str = "", initial: list[Path] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Elabora più file")
        self.resize(720, 560)
        self._current_settings = current_settings
        self._converter = converter
        self._use_converter = use_converter
        self._start_dir = start_dir
        self._task: Task | None = None
        self._queue: list[Path] = []
        self._results: list[tuple[Path, str, str]] = []
        self._outputs: list[Path] = []
        self._eta = EtaEstimator()
        self._started = 0.0
        self._closed = False
        self._preset_problem = ""

        v = QVBoxLayout(self)
        v.addWidget(QLabel("<b>Foto da elaborare</b>"))
        self.files = QListWidget()
        self.files.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        v.addWidget(self.files, 1)
        row = QHBoxLayout()
        add_files = QPushButton("Aggiungi foto…")
        add_files.clicked.connect(self._add_files)
        add_folder = QPushButton("Aggiungi cartella…")
        add_folder.clicked.connect(self._add_folder)
        self.recursive = QCheckBox("Includi le sottocartelle")
        remove = QPushButton("Rimuovi selezionate")
        remove.clicked.connect(self._remove_selected)
        clear = QPushButton("Svuota")
        clear.clicked.connect(lambda: (self.files.clear(), self._update_summary()))
        for w in (add_files, add_folder, self.recursive):
            row.addWidget(w)
        row.addStretch(1)
        row.addWidget(remove)
        row.addWidget(clear)
        v.addLayout(row)

        opts = QHBoxLayout()
        opts.addWidget(QLabel("Impostazioni:"))
        self.preset = QComboBox()
        self.preset.addItem("Quelle attuali della finestra principale", "")
        for name, (desc, _entry) in list_presets().items():
            self.preset.addItem(f"Preset «{name}»", name)
            self.preset.setItemData(self.preset.count() - 1, desc, Qt.ItemDataRole.ToolTipRole)
        self.preset.currentIndexChanged.connect(self._update_summary)
        opts.addWidget(self.preset, 1)
        opts.addWidget(QLabel("Se il file esiste:"))
        self.policy = QComboBox()
        for key, label in POLICIES.items():
            self.policy.addItem(label, key)
        opts.addWidget(self.policy)
        v.addLayout(opts)
        self.summary = hint_label()
        v.addWidget(self.summary)

        self.total = QProgressBar()
        self.total.setFormat("%v di %m foto")
        self.current = QProgressBar()
        self.current.setRange(0, 100)
        self.status = hint_label()
        for w in (self.total, self.current, self.status):
            v.addWidget(w)
            w.hide()

        buttons = QHBoxLayout()
        self.open_folder = QPushButton("Apri la cartella di uscita")
        self.open_folder.clicked.connect(self._open_output_folder)
        self.open_folder.hide()
        self.copy_errors = QPushButton("Copia l'elenco degli errori")
        self.copy_errors.clicked.connect(self._copy_errors)
        self.copy_errors.hide()
        buttons.addWidget(self.open_folder)
        buttons.addWidget(self.copy_errors)
        buttons.addStretch(1)
        self.start_button = QPushButton("Avvia")
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self._start)
        self.cancel_button = QPushButton("Annulla")
        self.cancel_button.clicked.connect(self._cancel_or_close)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.start_button)
        v.addLayout(buttons)

        for p in initial or []:
            self._add_paths([p])
        self._update_summary()

    # ------------------------------------------------------------------ scelta dei file

    def _add_paths(self, paths: list[Path]) -> None:
        present = {self.files.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.files.count())}
        for p in collect_inputs(paths, self.recursive.isChecked(), self._settings().output.folder):
            if str(p) not in present and is_supported(p):
                self.files.addItem(p.name if p.parent == Path(self._start_dir or ".") else str(p))
                self.files.item(self.files.count() - 1).setData(Qt.ItemDataRole.UserRole, str(p))
                present.add(str(p))
        self._update_summary()

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Foto da elaborare", self._start_dir, file_dialog_filter())
        self._add_paths([Path(p) for p in paths])

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Cartella da elaborare", self._start_dir)
        if folder:
            self._add_paths([Path(folder)])

    def _remove_selected(self) -> None:
        for item in self.files.selectedItems():
            self.files.takeItem(self.files.row(item))
        self._update_summary()

    def _settings(self) -> Settings:
        """Impostazioni da usare; se il preset scelto non è più leggibile si usano quelle attuali."""
        settings = self._current_settings()
        name = self.preset.currentData()
        self._preset_problem = ""
        if name:
            try:
                settings = apply_preset(settings, preset_content(list_presets()[name][1]))
            except (KeyError, PresetError, OSError, ValueError) as exc:
                self._preset_problem = f"Preset «{name}» non leggibile ({exc}): verranno usate le impostazioni attuali."
        return settings

    def _update_summary(self) -> None:
        s = self._settings()
        count = self.files.count()
        folder = s.output.folder or "stessa cartella della foto"
        algorithm = get_algorithm(s.denoise.algorithm)
        text = (f"{count} foto · metodo {algorithm.label} · formato {s.output.format.upper()} · "
                f"cartella «{folder}» · nome «{s.output.name_template}»")
        if not algorithm.is_available():
            text += f"<br><span style='color:#e0b050'>{algorithm.label} non è ancora scaricato: scaricalo dal pannello " \
                    "della finestra principale prima di avviare.</span>"
        if self._preset_problem:
            text += f"<br><span style='color:#e0b050'>{self._preset_problem}</span>"
        self.summary.setText(text)
        self.start_button.setEnabled(count > 0 and self._task is None and algorithm.is_available())

    # ------------------------------------------------------------------ esecuzione

    def _start(self) -> None:
        self._queue = [Path(self.files.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.files.count())]
        if not self._queue:
            return
        self._run_settings = self._settings()
        self._policy = self.policy.currentData()
        self._results.clear()
        self._outputs.clear()
        self._started = time.perf_counter()
        self.total.setRange(0, len(self._queue))
        self.total.setValue(0)
        for w in (self.total, self.current, self.status):
            w.show()
        self.open_folder.hide()
        self.copy_errors.hide()
        self.start_button.setEnabled(False)
        self.cancel_button.setText("Interrompi")
        self._index = 0
        self._next()

    def _next(self) -> None:
        if self._index >= len(self._queue):
            self._finish(interrupted=False)
            return
        path = self._queue[self._index]
        self.current.setValue(0)
        self._eta.reset()
        task = Task(process_one, path, self._run_settings, self._policy, self._converter, self._use_converter,
                    with_progress=True, taken=frozenset(self._outputs))
        task.signals.progress.connect(self._on_progress)
        task.signals.finished.connect(lambda res, p=path: self._done(p, res))
        task.signals.failed.connect(lambda msg, _d, p=path: self._done(p, ("errore", None, [msg])))
        task.signals.cancelled.connect(lambda: self._finish(interrupted=True))
        self._task = task
        start(task)

    def _on_progress(self, fraction: float, message: str) -> None:
        self.current.setValue(int(fraction * 100))
        done = self._index + fraction
        elapsed = time.perf_counter() - self._started
        eta = ""
        if done > 0.05 and elapsed > 2:
            eta = " · circa " + format_duration(elapsed * (len(self._queue) - done) / done) + " rimanenti in tutto"
        self.status.setText(f"{self._queue[self._index].name} ({self._index + 1} di {len(self._queue)}): {message}{eta}")

    def _done(self, path: Path, result) -> None:
        if self._closed:
            return
        outcome, saved, notes = result
        if outcome == "ok" and saved is not None:
            self._outputs.append(saved)
        self._results.append((path, outcome, "; ".join(notes)))
        self._index += 1
        self.total.setValue(self._index)
        self._task = None
        self._next()

    def _finish(self, interrupted: bool) -> None:
        if self._closed:
            return
        self._task = None
        ok = sum(1 for _, outcome, _ in self._results if outcome == "ok")
        skipped = sum(1 for _, outcome, _ in self._results if outcome == "saltata")
        errors = [(p, n) for p, outcome, n in self._results if outcome == "errore"]
        elapsed = format_duration(time.perf_counter() - self._started)
        head = "Interrotta" if interrupted else "Completata"
        text = f"<b>{head}: {ok} foto elaborate su {len(self._queue)} in {elapsed}.</b>"
        if skipped:
            text += f" {skipped} saltate perché già presenti."
        if errors:
            text += f" <span style='color:#e0b050'>{len(errors)} con errori:</span><br>" + "<br>".join(
                f"{p.name}: {n}" for p, n in errors[:8])
        self.status.setText(text)
        self.status.setTextFormat(Qt.TextFormat.RichText)
        self.current.hide()
        self.open_folder.setVisible(bool(self._outputs))
        self.copy_errors.setVisible(bool(errors))
        self.cancel_button.setText("Chiudi")
        self._update_summary()
        QApplication.alert(self)

    def _open_output_folder(self) -> None:
        if self._outputs:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._outputs[-1].parent)))

    def _copy_errors(self) -> None:
        lines = [f"{p}: {n}" for p, outcome, n in self._results if outcome == "errore"]
        QGuiApplication.clipboard().setText("\n".join(lines))

    def _cancel_or_close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self.cancel_button.setEnabled(False)
            self.status.setText("Interruzione in corso…")
            self.cancel_button.setEnabled(True)
        else:
            self.reject()

    def _stop(self) -> None:
        self._closed = True
        if self._task is not None:
            self._task.cancel()
            self._task = None
            self._queue = []  # nessuna foto successiva

    def reject(self) -> None:
        """Esc o chiusura: l'elaborazione viene interrotta, non lasciata girare di nascosto."""
        self._stop()
        super().reject()

    def closeEvent(self, event) -> None:
        self._stop()
        super().closeEvent(event)
