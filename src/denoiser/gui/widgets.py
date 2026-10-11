"""Controlli riutilizzabili del pannello delle impostazioni."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..algorithms import Param

_SLIDER_STEPS = 1000
#: Larghezza comune della colonna delle etichette: tutti i gruppi restano allineati.
LABEL_WIDTH = 128


class WheelGuard(QObject):
    """La rotellina cambia un valore solo se il controllo ha il fuoco: altrimenti scorre il pannello."""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 (API Qt)
        if event.type() == QEvent.Type.Wheel and isinstance(obj, QWidget) and not obj.hasFocus():
            event.ignore()
            return True
        return False


_WHEEL_GUARD = WheelGuard()


def guard_wheel(widget: QWidget) -> None:
    widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    widget.installEventFilter(_WHEEL_GUARD)


class ExplainFilter(QObject):
    """Mostra la spiegazione (tooltip) del controllo sotto il mouse in un riquadro fisso."""

    def __init__(self, show: Callable[[str], None]):
        super().__init__()
        self._show = show

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() in (QEvent.Type.Enter, QEvent.Type.FocusIn) and isinstance(obj, QWidget):
            widget: QWidget | None = obj
            while widget is not None and not widget.toolTip():
                widget = widget.parentWidget()
            if widget is not None:
                self._show(widget.toolTip())
        return False


def form_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setFixedWidth(LABEL_WIDTH)
    label.setWordWrap(True)
    return label


def make_form(parent: QWidget | None = None) -> QFormLayout:
    form = QFormLayout(parent)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    form.setHorizontalSpacing(10)
    form.setVerticalSpacing(6)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    return form


def hint_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    return label


class FloatControl(QWidget):
    """Cursore + casella numerica collegati, con didascalia opzionale.

    Con ``center`` il valore ``center`` cade a metà del cursore (scala non lineare): utile per
    le forze, dove 1 = «rumore misurato» deve essere il punto di riferimento visivo.
    Doppio clic sul cursore: torna al valore predefinito.
    """

    valueChanged = Signal(float)

    def __init__(
        self,
        minimum: float,
        maximum: float,
        step: float,
        value: float,
        decimals: int = 2,
        default: float | None = None,
        center: float | None = None,
        hint: str = "",
        suffix: str = "",
    ):
        super().__init__()
        self._min, self._max = minimum, maximum
        self._center = center
        self._default = value if default is None else default
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, _SLIDER_STEPS)
        if center is not None:
            self.slider.setTickPosition(QSlider.TickPosition.TicksBelow)
            self.slider.setTickInterval(_SLIDER_STEPS // 2)
        self.spin = QDoubleSpinBox()
        self.spin.setRange(minimum, maximum)
        self.spin.setSingleStep(step)
        self.spin.setDecimals(decimals)
        self.spin.setKeyboardTracking(False)
        self.spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.spin.setFixedWidth(64 if not suffix else 78)
        if suffix:
            self.spin.setSuffix(suffix)
        for w in (self.slider, self.spin):
            guard_wheel(w)
        self.slider.installEventFilter(self)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.slider, 1)
        row.addWidget(self.spin)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        layout.addLayout(row)
        self.hint = hint_label(hint)
        self.hint.setVisible(bool(hint))
        layout.addWidget(self.hint)
        self.set_value(value)
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)

    # ------------------------------------------------------------------ scala

    def _to_pos(self, value: float) -> int:
        lo, hi, c = self._min, self._max, self._center
        if c is None or not (lo < c < hi):
            frac = (value - lo) / ((hi - lo) or 1.0)
        elif value <= c:
            frac = 0.5 * (value - lo) / (c - lo)
        else:
            frac = 0.5 + 0.5 * (value - c) / (hi - c)
        return int(round(min(max(frac, 0.0), 1.0) * _SLIDER_STEPS))

    def _from_pos(self, pos: int) -> float:
        frac = pos / _SLIDER_STEPS
        lo, hi, c = self._min, self._max, self._center
        if c is None or not (lo < c < hi):
            return lo + (hi - lo) * frac
        if frac <= 0.5:
            return lo + (c - lo) * frac * 2
        return c + (hi - c) * (frac - 0.5) * 2

    # ------------------------------------------------------------------ API

    def value(self) -> float:
        return float(self.spin.value())

    def set_value(self, value: float) -> None:
        for w in (self.slider, self.spin):
            w.blockSignals(True)
        self.spin.setValue(value)
        self.slider.setValue(self._to_pos(self.spin.value()))
        for w in (self.slider, self.spin):
            w.blockSignals(False)

    def set_maximum(self, maximum: float) -> None:
        """Cambia il massimo (es. 1 per le reti «cieche»), limitando il valore se serve."""
        if maximum == self._max:
            return
        self._max = maximum
        self.spin.setMaximum(maximum)
        if self._center is not None and self._center >= maximum:
            self.slider.setTickPosition(QSlider.TickPosition.NoTicks)
        elif self._center is not None:
            self.slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        old = self.value()
        self.set_value(min(old, maximum))
        if self.value() != old:
            self.valueChanged.emit(self.value())

    def set_hint(self, text: str) -> None:
        self.hint.setText(text)
        self.hint.setVisible(bool(text))

    def reset(self) -> None:
        if self.value() != self._default:
            self.set_value(min(self._default, self._max))
            self.valueChanged.emit(self.value())

    def setToolTip(self, text: str) -> None:  # noqa: N802 (API Qt)
        super().setToolTip(text)
        self.slider.setToolTip(text)
        self.spin.setToolTip(text)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if obj is self.slider and event.type() == QEvent.Type.MouseButtonDblClick:
            self.reset()
            return True
        return False

    def _from_slider(self, pos: int) -> None:
        self.spin.blockSignals(True)
        self.spin.setValue(self._from_pos(pos))
        self.spin.blockSignals(False)
        self.valueChanged.emit(self.value())

    def _from_spin(self, value: float) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(self._to_pos(value))
        self.slider.blockSignals(False)
        self.valueChanged.emit(float(value))


def make_combo(choices: dict[str, str], current: Any, tooltips: dict[str, str] | None = None) -> QComboBox:
    combo = QComboBox()
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(8)
    for key, label in choices.items():
        combo.addItem(label, key)
        if tooltips and key in tooltips:
            combo.setItemData(combo.count() - 1, tooltips[key], Qt.ItemDataRole.ToolTipRole)
    set_combo(combo, current)
    guard_wheel(combo)
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
        layout = make_form(self)
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
            else:
                decimals = 0 if p.kind == "int" else 2
                w = FloatControl(
                    float(p.minimum or 0), float(p.maximum or 1), float(p.step or (1 if p.kind == "int" else 0.1)),
                    float(value), decimals=decimals, default=float(p.default),
                )
                w.valueChanged.connect(lambda *_: self.changed.emit())
            w.setToolTip(p.tooltip)
            label = form_label(p.label)
            label.setToolTip(p.tooltip)
            self._widgets[p.key] = w
            layout.addRow(label, w)

    def values(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for p in self._params:
            w = self._widgets[p.key]
            if isinstance(w, QComboBox):
                out[p.key] = w.currentData()
            elif isinstance(w, QCheckBox):
                out[p.key] = w.isChecked()
            elif p.kind == "int":
                out[p.key] = int(round(w.value()))
            else:
                out[p.key] = w.value()
        return out

    def reset(self) -> None:
        for p in self._params:
            w = self._widgets[p.key]
            if isinstance(w, QComboBox):
                set_combo(w, str(p.default))
            elif isinstance(w, QCheckBox):
                w.setChecked(bool(p.default))
            else:
                w.set_value(float(p.default))
        self.changed.emit()

    def install_filter(self, filt: QObject) -> None:
        for w in self.findChildren(QWidget):
            w.installEventFilter(filt)
