"""Vista prima/dopo con tendina divisoria trascinabile, zoom e spostamento."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QWidget

_HANDLE_TOLERANCE = 8
_MIN_ZOOM, _MAX_ZOOM = 0.02, 16.0


def to_qimage(rgb: np.ndarray) -> QImage:
    """Converte un array sRGB float [0, 1] (H, W, 3) in QImage (con copia dei dati)."""
    u8 = np.ascontiguousarray(np.clip(rgb * 255.0 + 0.5, 0, 255).astype(np.uint8))
    h, w = u8.shape[:2]
    return QImage(u8.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


class SplitView(QWidget):
    """A sinistra della linea l'originale, a destra il risultato del denoise."""

    #: Emesso quando cambia la zona visibile: (x, y, larghezza, altezza) in pixel dell'immagine.
    viewportChanged = Signal(int, int, int, int)
    zoomChanged = Signal(float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(320, 240)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._base: QImage | None = None
        self._patch: QImage | None = None
        self._patch_rect = QRect()
        self._zoom = 1.0
        self._offset = QPointF(0, 0)  # posizione sullo schermo del pixel (0, 0) dell'immagine
        self._split = 0.5  # posizione della linea come frazione della larghezza
        self._drag_mode: str | None = None
        self._drag_start = QPointF()
        self._offset_start = QPointF()
        self._message = ""

    # ------------------------------------------------------------------ contenuti

    def set_base(self, rgb: np.ndarray | None, keep_view: bool = False) -> None:
        self._base = to_qimage(rgb) if rgb is not None else None
        self._patch = None
        if not keep_view:
            self.fit()
        self.update()

    def set_patch(self, rgb: np.ndarray, rect: tuple[int, int, int, int]) -> None:
        self._patch = to_qimage(rgb)
        self._patch_rect = QRect(*rect)
        self.update()

    def clear_patch(self) -> None:
        self._patch = None
        self.update()

    def set_message(self, text: str) -> None:
        self._message = text
        self.update()

    def has_image(self) -> bool:
        return self._base is not None

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

    def zoom_to(self, zoom: float) -> None:
        self._set_zoom(zoom, QPointF(self.width() / 2, self.height() / 2))

    def _set_zoom(self, zoom: float, anchor: QPointF, center_image: bool = False) -> None:
        zoom = max(_MIN_ZOOM, min(_MAX_ZOOM, zoom))
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

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(40, 40, 40))
        if self._base is None:
            p.setPen(QColor(200, 200, 200))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Apri una foto (Ctrl+O) o trascinala qui")
            return
        smooth = self._zoom < 1.0
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, smooth)
        target = QRectF(self._offset, self._offset + QPointF(self._base.width(), self._base.height()) * self._zoom)
        p.drawImage(target, self._base)

        split_x = int(self.width() * self._split)
        if self._patch is not None:
            p.save()
            p.setClipRect(QRect(split_x, 0, self.width() - split_x, self.height()))
            r = self._patch_rect
            patch_target = QRectF(
                self._offset + QPointF(r.x(), r.y()) * self._zoom,
                self._offset + QPointF(r.x() + r.width(), r.y() + r.height()) * self._zoom,
            )
            p.drawImage(patch_target, self._patch)
            p.restore()

        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(QPen(QColor(255, 255, 255, 220), 2))
        p.drawLine(split_x, 0, split_x, self.height())
        handle = QRectF(split_x - 10, self.height() / 2 - 20, 20, 40)
        p.setBrush(QColor(255, 255, 255, 220))
        p.drawRoundedRect(handle, 6, 6)

        font = QFont(self.font())
        font.setBold(True)
        p.setFont(font)
        self._label(p, "Prima", QPointF(split_x - 12, 22), align_right=True)
        self._label(p, "Dopo", QPointF(split_x + 12, 22), align_right=False)
        if self._message:
            p.setPen(QColor(255, 230, 150))
            p.drawText(self.rect().adjusted(10, 0, -10, -10),
                       Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter, self._message)

    def _label(self, p: QPainter, text: str, pos: QPointF, align_right: bool) -> None:
        metrics = p.fontMetrics()
        w = metrics.horizontalAdvance(text) + 12
        rect = QRectF(pos.x() - w if align_right else pos.x(), pos.y() - 16, w, 22)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 150))
        p.drawRoundedRect(rect, 4, 4)
        p.setPen(QColor(255, 255, 255))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    # ------------------------------------------------------------------ interazione

    def _near_handle(self, x: float) -> bool:
        return abs(x - self.width() * self._split) <= _HANDLE_TOLERANCE

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._base is None:
            return
        pos = event.position()
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
        else:
            near = self._base is not None and self._near_handle(pos.x())
            self.setCursor(Qt.CursorShape.SplitHCursor if near else Qt.CursorShape.OpenHandCursor)

    def mouseReleaseEvent(self, _event) -> None:
        if self._drag_mode == "pan":
            self._emit_viewport()
        self._drag_mode = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, event) -> None:
        """Doppio clic: alterna tra adatta alla finestra e 100% nel punto cliccato."""
        if self._base is None:
            return
        if self._zoom < 0.99:
            self._set_zoom(1.0, event.position())
        else:
            self.fit()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._base is None:
            return
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        self._set_zoom(self._zoom * factor, event.position())

    def resizeEvent(self, _event) -> None:
        self._clamp_offset()
        self._emit_viewport()
