"""Vista prima/dopo con tendina divisoria, zoom a livelli fissi e modalità di confronto."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QKeyEvent, QPainter, QPainterPath, QPen, QWheelEvent
from PySide6.QtWidgets import QWidget

from .style import ACCENT, CANVAS

_HANDLE_TOLERANCE = 14
#: Livelli di zoom: la rotellina e Ctrl +/- si fermano sempre su questi valori.
ZOOM_STEPS = (0.0625, 0.125, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0)

MODES = {
    "split": "Tendina prima/dopo",
    "after": "Solo dopo",
    "before": "Solo prima",
    "diff": "Rumore tolto (differenza ×4)",
}


def to_qimage(rgb: np.ndarray) -> QImage:
    """Converte un array sRGB float [0, 1] (H, W, 3) in QImage (con copia dei dati)."""
    u8 = np.ascontiguousarray(np.clip(rgb * 255.0 + 0.5, 0, 255).astype(np.uint8))
    h, w = u8.shape[:2]
    return QImage(u8.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


class SplitView(QWidget):
    """A sinistra della linea l'originale, a destra il risultato del denoise."""

    #: (x, y, larghezza, altezza) della zona visibile in pixel dell'immagine.
    viewportChanged = Signal(int, int, int, int)
    zoomChanged = Signal(float)
    hintClicked = Signal()
    modeChanged = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(320, 240)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._base: QImage | None = None
        self._patch: QImage | None = None
        self._diff: QImage | None = None
        self._patch_rect = QRect()
        self._stale = False
        self._busy: float | None = None  # None = fermo, -1 = indeterminato, 0..1 = avanzamento
        self._busy_phase = 0.0
        self._busy_timer = QTimer(self, interval=40)
        self._busy_timer.timeout.connect(self._tick)
        self._zoom = 1.0
        self._offset = QPointF(0, 0)  # posizione sullo schermo del pixel (0, 0) dell'immagine
        self._split = 0.5
        self._mode = "split"
        self._peek = False  # Spazio tenuto premuto: si vede l'originale
        self._drag_mode: str | None = None
        self._drag_start = QPointF()
        self._offset_start = QPointF()
        self._hover_handle = False
        self._hint = ""
        self._hint_rect = QRectF()
        self._stats = ""
        self._overlay = ""  # messaggio centrale (es. apertura in corso)

    # ------------------------------------------------------------------ contenuti

    def set_base(self, rgb: np.ndarray | None, keep_view: bool = False) -> None:
        self._base = to_qimage(rgb) if rgb is not None else None
        if not keep_view:
            self._patch = self._diff = None
            self.fit()
        self.update()

    def set_patch(self, rgb: np.ndarray, rect: tuple[int, int, int, int], diff: np.ndarray | None = None) -> None:
        self._patch = to_qimage(rgb)
        self._diff = to_qimage(diff) if diff is not None else None
        self._patch_rect = QRect(*rect)
        self._stale = False
        self.update()

    def clear_patch(self) -> None:
        self._patch = self._diff = None
        self._stats = ""
        self.update()

    def mark_stale(self) -> None:
        """Il risultato mostrato non corrisponde più alle impostazioni: viene attenuato."""
        if self._patch is not None:
            self._stale = True
            self.update()

    def set_busy(self, fraction: float | None) -> None:
        self._busy = fraction
        if fraction is None:
            self._busy_timer.stop()
        elif not self._busy_timer.isActive():
            self._busy_timer.start()
        self.update()

    def set_hint(self, text: str) -> None:
        self._hint = text
        self.update()

    def set_stats(self, text: str) -> None:
        self._stats = text
        self.update()

    def set_overlay(self, text: str) -> None:
        self._overlay = text
        self.update()

    def has_image(self) -> bool:
        return self._base is not None

    def _tick(self) -> None:
        self._busy_phase = (self._busy_phase + 0.02) % 1.0
        self.update()

    # ------------------------------------------------------------------ modalità

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        if mode in MODES and mode != self._mode:
            self._mode = mode
            self.modeChanged.emit(mode)
            self.update()

    def cycle_mode(self) -> None:
        order = list(MODES)
        self.set_mode(order[(order.index(self._mode) + 1) % len(order)])

    def set_peek(self, on: bool) -> None:
        self._peek = on
        self.update()

    # ------------------------------------------------------------------ zoom

    @property
    def zoom(self) -> float:
        return self._zoom

    def fit(self) -> None:
        if self._base is None:
            return
        w, h = self._base.width(), self._base.height()
        zoom = min(self.width() / w, self.height() / h, 1.0)
        self._set_zoom(zoom, QPointF(self.width() / 2, self.height() / 2), center_image=True)

    def zoom_to(self, zoom: float, anchor: QPointF | None = None) -> None:
        self._set_zoom(zoom, anchor or QPointF(self.width() / 2, self.height() / 2))

    def zoom_step(self, direction: int, anchor: QPointF | None = None) -> None:
        current = self._zoom
        if direction > 0:
            target = next((z for z in ZOOM_STEPS if z > current * 1.001), ZOOM_STEPS[-1])
        else:
            target = next((z for z in reversed(ZOOM_STEPS) if z < current * 0.999), ZOOM_STEPS[0])
        self.zoom_to(target, anchor)

    def center_on(self, x: float, y: float) -> None:
        self._offset = QPointF(self.width() / 2 - x * self._zoom, self.height() / 2 - y * self._zoom)
        self._clamp_offset()
        self._emit_viewport()
        self.update()

    def _set_zoom(self, zoom: float, anchor: QPointF, center_image: bool = False) -> None:
        zoom = max(ZOOM_STEPS[0] / 2, min(ZOOM_STEPS[-1], zoom))
        if center_image and self._base is not None:
            self._zoom = zoom
            self._offset = QPointF(
                (self.width() - self._base.width() * zoom) / 2,
                (self.height() - self._base.height() * zoom) / 2,
            )
        else:
            image_point = (anchor - self._offset) / self._zoom
            self._zoom = zoom
            self._offset = anchor - image_point * zoom
        self._clamp_offset()
        self.zoomChanged.emit(self._zoom)
        self._emit_viewport()
        self.update()

    def _clamp_offset(self) -> None:
        if self._base is None:
            return
        w, h = self._base.width() * self._zoom, self._base.height() * self._zoom
        x, y = self._offset.x(), self._offset.y()
        x = (self.width() - w) / 2 if w <= self.width() else min(0, max(self.width() - w, x))
        y = (self.height() - h) / 2 if h <= self.height() else min(0, max(self.height() - h, y))
        self._offset = QPointF(x, y)

    def visible_image_rect(self) -> tuple[int, int, int, int] | None:
        if self._base is None:
            return None
        x0 = max(0, int(-self._offset.x() / self._zoom))
        y0 = max(0, int(-self._offset.y() / self._zoom))
        x1 = min(self._base.width(), int(np.ceil((self.width() - self._offset.x()) / self._zoom)))
        y1 = min(self._base.height(), int(np.ceil((self.height() - self._offset.y()) / self._zoom)))
        if x1 <= x0 or y1 <= y0:
            return None
        return x0, y0, x1 - x0, y1 - y0

    def _emit_viewport(self) -> None:
        rect = self.visible_image_rect()
        if rect is not None:
            self.viewportChanged.emit(*rect)

    # ------------------------------------------------------------------ disegno

    def _split_x(self) -> int:
        if self._peek or self._mode == "before":
            return self.width()
        if self._mode in ("after", "diff"):
            return 0
        return int(self.width() * self._split)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), CANVAS)
        if self._base is None:
            return
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self._zoom < 1.0)
        target = QRectF(self._offset, self._offset + QPointF(self._base.width(), self._base.height()) * self._zoom)
        p.fillRect(target.adjusted(-1, -1, 1, 1), QColor(0, 0, 0, 120))
        p.drawImage(target, self._base)

        split_x = self._split_x()
        after = QRectF(split_x, 0, self.width() - split_x, self.height())
        shown = self._diff if self._mode == "diff" and self._diff is not None else self._patch
        if split_x < self.width():
            p.save()
            p.setClipRect(after)
            if shown is not None:
                if self._stale:
                    p.setOpacity(0.55)
                r = self._patch_rect
                patch_target = QRectF(
                    self._offset + QPointF(r.x(), r.y()) * self._zoom,
                    self._offset + QPointF(r.x() + r.width(), r.y() + r.height()) * self._zoom,
                )
                p.drawImage(patch_target, shown)
                p.setOpacity(1.0)
            else:
                p.fillRect(after, QColor(0, 0, 0, 90))  # nessun risultato: lato «dopo» velato
            p.restore()
            if self._busy is not None:
                self._draw_busy(p, after)

        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._mode == "split" and not self._peek:
            self._draw_handle(p, split_x)
        self._draw_labels(p, split_x)
        if self._hint and split_x < self.width():
            self._draw_hint(p, after)
        else:
            self._hint_rect = QRectF()
        if self._overlay:
            self._pill(p, self._overlay, QPointF(self.width() / 2, self.height() / 2), size=11, center=True)

    def _draw_busy(self, p: QPainter, area: QRectF) -> None:
        bar = QRectF(area.x(), 0, area.width(), 3)
        p.fillRect(bar, QColor(255, 255, 255, 30))
        if self._busy is not None and self._busy >= 0:
            p.fillRect(QRectF(bar.x(), 0, bar.width() * self._busy, 3), QColor(ACCENT))
        else:
            seg = bar.width() * 0.25
            x = bar.x() + (bar.width() + seg) * self._busy_phase - seg
            p.fillRect(QRectF(max(bar.x(), x), 0, seg, 3), QColor(ACCENT))

    def _draw_handle(self, p: QPainter, split_x: int) -> None:
        p.setPen(QPen(QColor(0, 0, 0, 110), 4))
        p.drawLine(split_x, 0, split_x, self.height())
        p.setPen(QPen(QColor(255, 255, 255, 230), 1.5))
        p.drawLine(split_x, 0, split_x, self.height())
        radius = 16 if self._hover_handle else 14
        center = QPointF(split_x, self.height() / 2)
        p.setBrush(QColor(30, 30, 30, 210))
        p.drawEllipse(center, radius, radius)
        path = QPainterPath()
        path.moveTo(center + QPointF(-3, -5)); path.lineTo(center + QPointF(-8, 0)); path.lineTo(center + QPointF(-3, 5))
        path.moveTo(center + QPointF(3, -5)); path.lineTo(center + QPointF(8, 0)); path.lineTo(center + QPointF(3, 5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

    def _after_label(self) -> str:
        if self._mode == "diff":
            return "RUMORE TOLTO ×4"
        if self._busy is not None:
            return "DOPO · CALCOLO" + (f" {int(self._busy * 100)}%" if self._busy >= 0 else "…")
        if self._patch is None:
            return "DOPO · NON CALCOLATO"
        if self._stale:
            return "DOPO · DA AGGIORNARE"
        return "DOPO" + (f" · {self._stats}" if self._stats else "")

    def _draw_labels(self, p: QPainter, split_x: int) -> None:
        font = QFont(self.font())
        font.setBold(True)
        font.setPointSizeF(8.5)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.5)
        p.setFont(font)
        metrics = p.fontMetrics()
        if self._peek or self._mode == "before":
            self._tag(p, "PRIMA (ORIGINALE)", 10, metrics)
            return
        after = self._after_label()
        if self._mode in ("after", "diff"):
            self._tag(p, after, 10, metrics)
            return
        before_w = metrics.horizontalAdvance("PRIMA") + 14
        after_w = metrics.horizontalAdvance(after) + 14
        if split_x - 12 >= before_w + 8:
            self._tag(p, "PRIMA", split_x - 12 - before_w, metrics)
        if self.width() - split_x - 12 >= after_w + 8:
            self._tag(p, after, split_x + 12, metrics)

    def _tag(self, p: QPainter, text: str, x: float, metrics) -> None:
        w = metrics.horizontalAdvance(text) + 14
        x = min(max(8, x), self.width() - 8 - w)
        rect = QRectF(x, 10, w, 22)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 160))
        p.drawRoundedRect(rect, 3, 3)
        p.setPen(QColor(255, 255, 255))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    def _pill(self, p: QPainter, text: str, anchor: QPointF, size: float = 9.5, center: bool = False) -> QRectF:
        font = QFont(self.font())
        font.setPointSizeF(size)
        p.setFont(font)
        metrics = p.fontMetrics()
        w = min(metrics.horizontalAdvance(text) + 28, self.width() - 20)
        h = metrics.height() + 16
        rect = QRectF(anchor.x() - w / 2, anchor.y() - (h / 2 if center else h), w, h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 175))
        p.drawRoundedRect(rect, 8, 8)
        p.setPen(QColor(255, 255, 255))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)
        return rect

    def _draw_hint(self, p: QPainter, area: QRectF) -> None:
        anchor = QPointF(area.center().x(), self.height() / 2)
        self._hint_rect = self._pill(p, self._hint, anchor, size=10, center=True)
        p.setPen(QPen(QColor(ACCENT), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(self._hint_rect, 8, 8)

    # ------------------------------------------------------------------ interazione

    def _near_handle(self, x: float) -> bool:
        return self._mode == "split" and abs(x - self.width() * self._split) <= _HANDLE_TOLERANCE

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._base is None:
            return
        pos = event.position()
        if self._hint and self._hint_rect.contains(pos):
            self.hintClicked.emit()
            return
        self._drag_mode = "split" if self._near_handle(pos.x()) else "pan"
        self._drag_start = pos
        self._offset_start = QPointF(self._offset)
        if self._drag_mode == "pan":
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        pos = event.position()
        if self._drag_mode == "split":
            self._split = min(1.0, max(0.0, pos.x() / max(1, self.width())))
            self.update()
        elif self._drag_mode == "pan":
            self._offset = self._offset_start + (pos - self._drag_start)
            self._clamp_offset()
            self.update()
        elif self._base is not None:
            near = self._near_handle(pos.x())
            if near != self._hover_handle:
                self._hover_handle = near
                self.update()
            if self._hint and self._hint_rect.contains(pos):
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.setCursor(Qt.CursorShape.SplitHCursor if near else Qt.CursorShape.OpenHandCursor)

    def mouseReleaseEvent(self, _event) -> None:
        if self._drag_mode == "pan":
            self._emit_viewport()
        self._drag_mode = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, event) -> None:
        """Doppio clic: 100% nel punto cliccato, oppure di nuovo adatta alla finestra."""
        if self._base is None:
            return
        if self._near_handle(event.position().x()):
            self._split = 0.5
            self.update()
        elif self._zoom < 0.99:
            self._set_zoom(1.0, event.position())
        else:
            self.fit()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._base is None:
            return
        self.zoom_step(1 if event.angleDelta().y() > 0 else -1, event.position())

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.set_peek(True)
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down) and self._base is not None:
            step = 200 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 60
            dx = {Qt.Key.Key_Left: step, Qt.Key.Key_Right: -step}.get(key, 0)
            dy = {Qt.Key.Key_Up: step, Qt.Key.Key_Down: -step}.get(key, 0)
            self._offset += QPointF(dx, dy)
            self._clamp_offset()
            self._emit_viewport()
            self.update()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.set_peek(False)
        else:
            super().keyReleaseEvent(event)

    def resizeEvent(self, _event) -> None:
        self._clamp_offset()
        self._emit_viewport()
