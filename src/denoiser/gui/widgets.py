"""Controlli riutilizzabili del pannello delle impostazioni."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QSlider,
    QSpinBox,
    QWidget,
)

from ..algorithms import Param

_SLIDER_STEPS = 1000


class FloatControl(QWidget):
    """Cursore + casella numerica collegati."""

    valueChanged = Signal(float)

    def __init__(self, minimum: float, maximum: float, step: float, value: float, decimals: int = 2):
        super().__init__()
        self._min, self._max = minimum, maximum
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, _SLIDER_STEPS)
        self.spin = QDoubleSpinBox()
        self.spin.setRange(minimum, maximum)
        self.spin.setSingleStep(step)
        self.spin.setDecimals(decimals)
        self.spin.setKeyboardTracking(False)
        self.spin.setFixedWidth(80)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.spin)
        self.set_value(value)
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)

    def value(self) -> float:
        return float(self.spin.value())

    def set_value(self, value: float) -> None:
        for w in (self.slider, self.spin):
            w.blockSignals(True)
        self.spin.setValue(value)
        span = self._max - self._min or 1.0
        self.slider.setValue(int(round((value - self._min) / span * _SLIDER_STEPS)))
        for w in (self.slider, self.spin):
            w.blockSignals(False)

    def setToolTip(self, text: str) -> None:  # noqa: N802 (API Qt)
        super().setToolTip(text)
        self.slider.setToolTip(text)
        self.spin.setToolTip(text)

    def _from_slider(self, pos: int) -> None:
        value = self._min + (self._max - self._min) * pos / _SLIDER_STEPS
        self.spin.blockSignals(True)
        self.spin.setValue(value)
        self.spin.blockSignals(False)
        self.valueChanged.emit(self.value())

    def _from_spin(self, value: float) -> None:
        self.slider.blockSignals(True)
        span = self._max - self._min or 1.0
        self.slider.setValue(int(round((value - self._min) / span * _SLIDER_STEPS)))
        self.slider.blockSignals(False)
        self.valueChanged.emit(float(value))


def make_combo(choices: dict[str, str], current: str) -> QComboBox:
    combo = QComboBox()
    for key, label in choices.items():
        combo.addItem(label, key)
    set_combo(combo, current)
    return combo


def set_combo(combo: QComboBox, key: Any) -> None:
    index = combo.findData(key)
    if index >= 0:
        combo.blockSignals(True)
        combo.setCurrentIndex(index)
        combo.blockSignals(False)


class ParamForm(QWidget):
    """Costruisce automaticamente i controlli per i parametri di un algoritmo."""

    changed = Signal()

    def __init__(self, params: tuple[Param, ...], values: dict[str, Any]):
        super().__init__()
        self._params = params
        self._widgets: dict[str, QWidget] = {}
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for p in params:
            value = values.get(p.key, p.default)
            if p.kind == "choice":
                w = make_combo(p.choices or {}, str(value))
                w.currentIndexChanged.connect(lambda *_: self.changed.emit())
            elif p.kind == "bool":
                w = QCheckBox()
                w.setChecked(bool(value))
                w.toggled.connect(lambda *_: self.changed.emit())
            elif p.kind == "int":
                w = QSpinBox()
                w.setRange(int(p.minimum or 0), int(p.maximum or 100))
                w.setSingleStep(int(p.step or 1))
                w.setValue(int(value))
                w.setKeyboardTracking(False)
                w.valueChanged.connect(lambda *_: self.changed.emit())
            else:
                w = FloatControl(float(p.minimum or 0), float(p.maximum or 1), float(p.step or 0.1), float(value))
                w.valueChanged.connect(lambda *_: self.changed.emit())
            w.setToolTip(p.tooltip)
            self._widgets[p.key] = w
            layout.addRow(p.label, w)

    def values(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for p in self._params:
            w = self._widgets[p.key]
            if isinstance(w, QComboBox):
                out[p.key] = w.currentData()
            elif isinstance(w, QCheckBox):
                out[p.key] = w.isChecked()
            elif isinstance(w, QSpinBox):
                out[p.key] = w.value()
            else:
                out[p.key] = w.value()
        return out
