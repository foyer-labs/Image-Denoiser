"""Finestra principale dell'applicazione."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QProgressDialog,
    QScrollArea,
    QToolBar,
)

from .. import __version__
from ..batch import process_file, save_result
from ..image import ImageData
from ..io import load_image
from ..io.dng_converter import find_converter
from ..io.formats import file_dialog_filter, is_supported
from ..io.naming import output_path, unique_path
from ..pipeline import Analysis, analyze, render, uses_sensor_stage
from ..presets import list_presets, load_preset, save_preset, user_presets_dir
from ..settings import Settings
from .settings_panel import SettingsPanel
from .split_view import SplitView
from .workers import Task, start

#: Oltre questa area la zona visibile non viene elaborata in anteprima (si chiede di ingrandire).
PREVIEW_MAX_PIXELS = 3_000_000
_DEBOUNCE_MS = 250


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Denoiser")
        self.resize(1400, 900)
        self.setAcceptDrops(True)
        self._qsettings = QSettings("Denoiser", "Denoiser")
        self._tasks: set[Task] = set()
        self._image: ImageData | None = None
        self._analysis: Analysis | None = None
        self._path: Path | None = None
        self._generation = 0  # cambia a ogni nuova foto: i risultati vecchi vengono scartati
        self._preview_running = False
        self._preview_pending = False
        self._base_running = False

        self.view = SplitView()
        self.setCentralWidget(self.view)
        self.panel = SettingsPanel(self._load_last_settings())
        scroll = QScrollArea()
        scroll.setWidget(self.panel)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(400)
        dock = QDockWidget("Impostazioni")
        dock.setWidget(scroll)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

        self.progress = QProgressBar()
        self.progress.setMaximumWidth(260)
        self.progress.setRange(0, 100)
        self.progress.hide()
        self.zoom_label = QLabel()
        self.statusBar().addPermanentWidget(self.zoom_label)
        self.statusBar().addPermanentWidget(self.progress)

        self._build_toolbar()
        self._preview_timer = QTimer(self, singleShot=True, interval=_DEBOUNCE_MS)
        self._preview_timer.timeout.connect(self._start_preview)
        self.view.viewportChanged.connect(lambda *_: self._schedule_preview())
        self.view.zoomChanged.connect(lambda z: self.zoom_label.setText(f"Zoom {z * 100:.0f}%"))
        self.panel.denoiseChanged.connect(self._on_settings_changed)
        self.panel.toneChanged.connect(self._on_tone_changed)
        self.panel.developChanged.connect(self._reload)
        self.panel.outputChanged.connect(self._save_last_settings)
        self.panel.dngConverterChanged.connect(self._set_dng_converter)
        self.panel.set_dng_converter(str(self._dng_converter() or ""))

    # ------------------------------------------------------------------ interfaccia

    def _build_toolbar(self) -> None:
        bar = QToolBar("Principale")
        bar.setMovable(False)
        self.addToolBar(bar)

        def action(text: str, slot, shortcut: str | None = None, tip: str = "") -> QAction:
            act = QAction(text, self)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            act.setToolTip(tip or text)
            act.triggered.connect(slot)
            bar.addAction(act)
            return act

        action("Apri…", self._open_dialog, "Ctrl+O", "Apri una foto (RAW, JPG, PNG, TIFF)")
        self.export_action = action("Esporta", self._export, "Ctrl+E", "Salva la foto elaborata con le impostazioni di uscita")
        action("Elabora più file…", self._batch, "Ctrl+B", "Applica le impostazioni correnti a più foto")
        bar.addSeparator()
        action("Adatta", lambda: self.view.fit(), "Ctrl+0", "Adatta alla finestra")
        action("100%", lambda: self.view.zoom_to(1.0), "Ctrl+1", "Pixel reali: il modo giusto per giudicare il rumore")
        bar.addSeparator()
        bar.addWidget(QLabel(" Preset: "))
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(170)
        self.preset_combo.activated.connect(self._apply_preset)
        bar.addWidget(self.preset_combo)
        action("Salva preset…", self._save_preset, None, "Salva le impostazioni correnti come preset")
        bar.addSeparator()
        action("Informazioni", self._about)
        self._refresh_presets()

    def _refresh_presets(self) -> None:
        self.preset_combo.clear()
        self.preset_combo.addItem("— scegli —", None)
        for name in list_presets():
            self.preset_combo.addItem(name, name)

    # ------------------------------------------------------------------ apertura

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        supported = [p for p in paths if is_supported(p)]
        if supported:
            self.open_path(supported[0])

    def _open_dialog(self) -> None:
        start_dir = self._qsettings.value("ultima_cartella", "")
        path, _ = QFileDialog.getOpenFileName(self, "Apri foto", start_dir, file_dialog_filter())
        if path:
            self.open_path(Path(path))

    def open_path(self, path: Path) -> None:
        self._path = path
        self._qsettings.setValue("ultima_cartella", str(path.parent))
        self.setWindowTitle(f"Denoiser — {path.name}")
        self._reload(reset_view=True)

    def _reload(self, reset_view: bool = False) -> None:
        """(Ri)carica la foto: necessario all'apertura e quando cambiano le impostazioni di sviluppo RAW."""
        if self._path is None:
            return
        self._generation += 1
        generation = self._generation
        settings = self.panel.settings()
        self._busy(f"Apertura di {self._path.name}…")

        def load(path: Path, develop, converter):
            image = load_image(path, develop, converter_path=converter)
            return image, analyze(image)

        task = Task(load, self._path, settings.develop, self._dng_converter())
        task.signals.finished.connect(lambda res: self._on_loaded(generation, res, reset_view))
        task.signals.failed.connect(lambda msg: self._on_failed("Impossibile aprire la foto", msg))
        self._run(task)

    def _on_loaded(self, generation: int, result, reset_view: bool) -> None:
        if generation != self._generation:
            return
        self._image, self._analysis = result
        self._update_info()
        self._refresh_base(reset_view=reset_view)

    def _update_info(self) -> None:
        image, analysis = self._image, self._analysis
        if image is None or analysis is None:
            return
        m = image.meta
        lines = [f"<b>{m.source.name}</b>", f"{image.width} × {image.height} px, {m.bits_per_sample} bit"]
        if m.camera:
            lines.append(m.camera)
        if m.iso:
            lines.append(f"ISO {m.iso:g}")
        if image.domain.value == "linear":
            sensor = f"sensore Bayer {m.cfa_pattern}" if m.cfa_pattern else "sensore non Bayer: denoise di livello 2"
            lines.append(sensor)
            stage = "livello 3 (dati del sensore)" if uses_sensor_stage(image, self.panel.settings()) else "livello 2 (immagine sviluppata)"
            lines.append(f"Denoise: {stage}")
        lines.append(analysis.describe())
        lines.extend(f"<i>{note}</i>" for note in m.notes)
        is_raw = image.domain.value == "linear"
        self.panel.set_image_info("<br>".join(lines), is_raw=is_raw, is_bayer=image.raw_source is not None)

    # ------------------------------------------------------------------ anteprima

    def _refresh_base(self, reset_view: bool = False) -> None:
        """Immagine "prima" a piena risoluzione (sviluppo/tonalità, senza denoise)."""
        if self._image is None or self._analysis is None:
            return
        generation = self._generation
        image, analysis, settings = self._image, self._analysis, self.panel.settings()
        self._busy("Preparazione dell'immagine…")
        task = Task(render, image, analysis, settings, None, False)
        task.signals.finished.connect(lambda rgb: self._on_base(generation, rgb, reset_view))
        task.signals.failed.connect(lambda msg: self._on_failed("Errore di visualizzazione", msg))
        self._run(task)

    def _on_base(self, generation: int, rgb, reset_view: bool) -> None:
        if generation != self._generation:
            return
        self._idle()
        self.view.set_base(rgb, keep_view=not reset_view)
        self._schedule_preview()

    def _schedule_preview(self) -> None:
        if self._image is not None:
            self._preview_timer.start()

    def _on_settings_changed(self) -> None:
        self._save_last_settings()
        self._update_info()
        self._schedule_preview()

    def _on_tone_changed(self) -> None:
        self._save_last_settings()
        self._refresh_base()

    def _start_preview(self) -> None:
        if self._image is None or self._analysis is None or not self.view.has_image():
            return
        if self._preview_running:
            self._preview_pending = True
            return
        rect = self.view.visible_image_rect()
        if rect is None:
            return
        if rect[2] * rect[3] > PREVIEW_MAX_PIXELS:
            self.view.clear_patch()
            self.view.set_message("Ingrandisci (Ctrl+1 o doppio clic) per vedere l'anteprima del denoise")
            return
        self.view.set_message("")
        self._preview_running = True
        generation = self._generation
        task = Task(render, self._image, self._analysis, self.panel.settings(), rect, True, with_progress=True)
        task.signals.progress.connect(self._on_progress)
        task.signals.finished.connect(lambda rgb: self._on_preview(generation, rgb, rect))
        task.signals.failed.connect(self._on_preview_failed)
        self.statusBar().showMessage("Calcolo dell'anteprima…")
        self._run(task)

    def _on_preview(self, generation: int, rgb, rect) -> None:
        self._preview_running = False
        self.progress.hide()
        self.statusBar().clearMessage()
        if generation == self._generation:
            self.view.set_patch(rgb, rect)
        if self._preview_pending:
            self._preview_pending = False
            self._start_preview()

    def _on_preview_failed(self, message: str) -> None:
        self._preview_running = False
        self._preview_pending = False
        self._on_failed("Errore nell'anteprima", message)

    # ------------------------------------------------------------------ esportazione

    def _export(self) -> None:
        if self._image is None or self._analysis is None:
            QMessageBox.information(self, "Esporta", "Apri prima una foto.")
            return
        settings = self.panel.settings()
        destination = output_path(self._image.meta, settings.output, settings.denoise.algorithm)
        if destination.exists() and not settings.output.overwrite:
            box = QMessageBox(self)
            box.setWindowTitle("File esistente")
            box.setText(f"{destination.name} esiste già.")
            overwrite = box.addButton("Sovrascrivi", QMessageBox.ButtonRole.DestructiveRole)
            rename = box.addButton("Salva con un altro nome", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Annulla", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is rename:
                destination = unique_path(destination)
            elif box.clickedButton() is not overwrite:
                return
        settings.output.overwrite = True  # la scelta è già stata fatta qui
        image, analysis = self._image, self._analysis
        self._busy(f"Esportazione di {destination.name}…")

        def export(progress=None):
            pixels = render(image, analysis, settings, progress=progress)
            return save_result(image, pixels, settings, destination)

        task = Task(export, with_progress=True)
        task.signals.progress.connect(self._on_progress)
        task.signals.finished.connect(self._on_exported)
        task.signals.failed.connect(lambda msg: self._on_failed("Esportazione non riuscita", msg))
        self._run(task)

    def _on_exported(self, path: Path) -> None:
        self._idle()
        self.statusBar().showMessage(f"Salvato: {path}", 8000)

    def _batch(self) -> None:
        start_dir = self._qsettings.value("ultima_cartella", "")
        paths, _ = QFileDialog.getOpenFileNames(self, "Foto da elaborare", start_dir, file_dialog_filter())
        if not paths:
            return
        settings = self.panel.settings()
        dialog = QProgressDialog("Elaborazione…", "Interrompi", 0, len(paths), self)
        dialog.setWindowTitle("Elaborazione di più file")
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(0)
        state = {"index": 0, "errors": []}
        converter = self._dng_converter()

        def next_file() -> None:
            i = state["index"]
            if dialog.wasCanceled() or i >= len(paths):
                dialog.close()
                done = i - len(state["errors"])
                text = f"Elaborate {done} foto su {len(paths)}."
                if state["errors"]:
                    text += "\n\nErrori:\n" + "\n".join(state["errors"][:10])
                QMessageBox.information(self, "Elaborazione completata", text)
                return
            dialog.setLabelText(f"{Path(paths[i]).name} ({i + 1} di {len(paths)})")
            dialog.setValue(i)
            task = Task(process_file, paths[i], settings, converter)
            task.signals.finished.connect(on_done)
            task.signals.failed.connect(lambda msg: on_done(None, msg))
            self._run(task)

        def on_done(result, failure: str | None = None) -> None:
            name = Path(paths[state["index"]]).name
            if failure or (result is not None and not result.ok):
                state["errors"].append(f"{name}: {failure or result.error}")
            state["index"] += 1
            next_file()

        next_file()

    # ------------------------------------------------------------------ preset e impostazioni

    def _apply_preset(self) -> None:
        name = self.preset_combo.currentData()
        if not name:
            return
        value = list_presets()[name]
        preset = load_preset(value) if isinstance(value, Path) else value
        # I preset predefiniti cambiano solo il denoise; quelli dell'utente tutto.
        current = self.panel.settings()
        if not isinstance(value, Path):
            merged = current.to_dict()
            merged["denoise"] = preset.to_dict()["denoise"]
            preset = Settings.from_dict(merged)
        develop_changed = preset.develop != current.develop
        self.panel.set_settings(preset)
        self._save_last_settings()
        if develop_changed:
            self._reload()
        else:
            self._refresh_base()
            self._update_info()

    def _save_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "Salva preset", "Nome del preset:")
        if ok and name.strip():
            path = save_preset(self.panel.settings(), user_presets_dir() / name.strip())
            self._refresh_presets()
            self.statusBar().showMessage(f"Preset salvato in {path}", 6000)

    def _load_last_settings(self) -> Settings:
        raw = self._qsettings.value("ultime_impostazioni", "")
        try:
            return Settings.from_dict(json.loads(raw)) if raw else Settings()
        except (ValueError, TypeError):
            return Settings()

    def _save_last_settings(self) -> None:
        self._qsettings.setValue("ultime_impostazioni", json.dumps(self.panel.settings().to_dict()))

    def _dng_converter(self) -> Path | None:
        return find_converter(self._qsettings.value("dng_converter", "") or None)

    def _set_dng_converter(self, path: str) -> None:
        self._qsettings.setValue("dng_converter", path)
        self.panel.set_dng_converter(str(self._dng_converter() or ""))

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "Denoiser",
            f"<b>Denoiser {__version__}</b><br>Riduzione del rumore per foto RAW, JPG e PNG, "
            "interamente in locale.<br><br>Doppio clic sull'immagine: 100% / adatta. "
            "Rotellina: zoom. Trascina: sposta. Trascina la linea bianca: confronto prima/dopo.",
        )

    # ------------------------------------------------------------------ utilità

    def _run(self, task: Task) -> None:
        self._tasks.add(task)
        task.signals.finished.connect(lambda *_: self._tasks.discard(task))
        task.signals.failed.connect(lambda *_: self._tasks.discard(task))
        start(task)

    def _busy(self, message: str) -> None:
        self.statusBar().showMessage(message)
        self.progress.setRange(0, 0)
        self.progress.show()

    def _idle(self) -> None:
        self.progress.hide()
        self.statusBar().clearMessage()

    def _on_progress(self, fraction: float, message: str) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(int(fraction * 100))
        self.progress.show()
        self.statusBar().showMessage(message)

    def _on_failed(self, title: str, message: str) -> None:
        self._idle()
        QMessageBox.warning(self, title, message)

    def closeEvent(self, event) -> None:
        self._save_last_settings()
        super().closeEvent(event)
