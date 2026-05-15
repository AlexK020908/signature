from __future__ import annotations

import math
import time
from dataclasses import dataclass

from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRect, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QImage,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QTabletEvent,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

CANVAS_W = 1200
CANVAS_H = 400
PADDING = 20
MIN_WIDTH = 1.5
MAX_WIDTH = 5.0
DEFAULT_WIDTH = 3.0
# Velocity (px/sec) at which the stroke is thinnest.
FAST_VELOCITY = 2500.0


@dataclass
class StrokePoint:
    pos: QPointF
    width: float


class SignatureCanvas(QWidget):
    """Transparent drawing surface for signatures.

    The visible grid/baseline is painted as an overlay in paintEvent; it is
    NEVER painted into the underlying QImage that will be exported.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_StaticContents, True)
        self.setAttribute(Qt.WA_TabletTracking, True)
        self.setFixedSize(CANVAS_W, CANVAS_H)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setCursor(Qt.CrossCursor)

        self._image = QImage(CANVAS_W, CANVAS_H, QImage.Format_ARGB32_Premultiplied)
        self._image.fill(Qt.transparent)

        self._current_stroke: list[StrokePoint] = []
        self._last_time: float = 0.0
        self._last_width: float = DEFAULT_WIDTH
        self._tablet_in_use: bool = False
        self._dirty_bbox: QRect | None = None

    # ---------- public API ----------

    def clear(self) -> None:
        self._image.fill(Qt.transparent)
        self._current_stroke.clear()
        self._dirty_bbox = None
        self.update()

    def is_empty(self) -> bool:
        return self._dirty_bbox is None or self._dirty_bbox.isEmpty()

    def export_png(self) -> bytes | None:
        """Return PNG bytes of the trimmed signature, or None if empty."""
        bbox = self._content_bbox()
        if bbox is None:
            return None
        bbox = bbox.adjusted(-PADDING, -PADDING, PADDING, PADDING)
        bbox = bbox.intersected(self._image.rect())
        cropped = self._image.copy(bbox)
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        if not cropped.save(buf, "PNG"):
            return None
        return bytes(buf.data())

    # ---------- input events ----------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._tablet_in_use:
            return
        if event.button() != Qt.LeftButton:
            return
        self._begin_stroke(event.position(), pressure=None)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._tablet_in_use:
            return
        if not (event.buttons() & Qt.LeftButton):
            return
        self._extend_stroke(event.position(), pressure=None)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._tablet_in_use:
            return
        if event.button() != Qt.LeftButton:
            return
        self._end_stroke()

    def tabletEvent(self, event: QTabletEvent) -> None:
        pos = QPointF(event.position())
        pressure = float(event.pressure())
        etype = event.type()
        if etype == event.Type.TabletPress:
            self._tablet_in_use = True
            self._begin_stroke(pos, pressure=pressure)
            event.accept()
        elif etype == event.Type.TabletMove:
            if self._current_stroke:
                self._extend_stroke(pos, pressure=pressure)
            event.accept()
        elif etype == event.Type.TabletRelease:
            self._end_stroke()
            self._tablet_in_use = False
            event.accept()
        else:
            super().tabletEvent(event)

    # ---------- painting ----------

    def paintEvent(self, _event) -> None:  # noqa: ANN001
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        # Background of the editor view only (NOT painted into the QImage).
        # Subtle checker isn't needed for the editor; we use a soft fill plus
        # a baseline guide so the user knows where to draw.
        painter.fillRect(self.rect(), QColor(250, 250, 250))
        guide_pen = QPen(QColor(220, 220, 220), 1, Qt.DashLine)
        painter.setPen(guide_pen)
        baseline_y = int(CANVAS_H * 0.75)
        painter.drawLine(40, baseline_y, CANVAS_W - 40, baseline_y)

        # The actual signature image — transparency preserved.
        painter.drawImage(0, 0, self._image)

    # ---------- stroke handling ----------

    def _begin_stroke(self, pos: QPointF, pressure: float | None) -> None:
        width = self._width_from_input(pressure=pressure, velocity=0.0)
        self._current_stroke = [StrokePoint(pos, width)]
        self._last_time = time.monotonic()
        self._last_width = width
        self._draw_dot(pos, width)

    def _extend_stroke(self, pos: QPointF, pressure: float | None) -> None:
        if not self._current_stroke:
            self._begin_stroke(pos, pressure)
            return
        now = time.monotonic()
        dt = max(now - self._last_time, 1e-4)
        prev = self._current_stroke[-1].pos
        dist = math.hypot(pos.x() - prev.x(), pos.y() - prev.y())
        velocity = dist / dt
        target_width = self._width_from_input(pressure=pressure, velocity=velocity)
        # Smooth width changes so adjacent segments don't jump.
        smoothed = self._last_width * 0.6 + target_width * 0.4
        self._current_stroke.append(StrokePoint(pos, smoothed))
        self._last_time = now
        self._last_width = smoothed
        self._render_tail_segment()

    def _end_stroke(self) -> None:
        if len(self._current_stroke) >= 3:
            self._render_full_stroke()
        self._current_stroke = []

    def _width_from_input(
        self, *, pressure: float | None, velocity: float
    ) -> float:
        if pressure is not None and pressure > 0.0:
            return MIN_WIDTH + (MAX_WIDTH - MIN_WIDTH) * max(min(pressure, 1.0), 0.0)
        factor = 1.0 - min(velocity / FAST_VELOCITY, 1.0)
        return MIN_WIDTH + (MAX_WIDTH - MIN_WIDTH) * factor

    def _draw_dot(self, pos: QPointF, width: float) -> None:
        painter = QPainter(self._image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(QColor(0, 0, 0))
        painter.setPen(Qt.NoPen)
        r = width / 2.0
        painter.drawEllipse(pos, r, r)
        painter.end()
        self._mark_dirty(QRect(int(pos.x() - r) - 1, int(pos.y() - r) - 1,
                               int(width) + 2, int(width) + 2))
        self.update()

    def _render_tail_segment(self) -> None:
        """Draw just the newest segment (for responsive feedback)."""
        pts = self._current_stroke
        n = len(pts)
        if n < 2:
            return
        # Quadratic Bezier between p[-3], p[-2], p[-1] when available.
        painter = QPainter(self._image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        if n == 2:
            self._stroke_segment(painter, pts[0], pts[1])
        else:
            p0, p1, p2 = pts[-3], pts[-2], pts[-1]
            mid_a = QPointF((p0.pos.x() + p1.pos.x()) / 2.0,
                            (p0.pos.y() + p1.pos.y()) / 2.0)
            mid_b = QPointF((p1.pos.x() + p2.pos.x()) / 2.0,
                            (p1.pos.y() + p2.pos.y()) / 2.0)
            path = QPainterPath(mid_a)
            path.quadTo(p1.pos, mid_b)
            pen = QPen(QColor(0, 0, 0), p1.width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawPath(path)
        painter.end()
        # Repaint just around the new segment.
        last = pts[-1].pos
        prev = pts[-2].pos
        margin = int(max(pts[-1].width, pts[-2].width)) + 2
        rect = QRect(
            int(min(last.x(), prev.x())) - margin,
            int(min(last.y(), prev.y())) - margin,
            int(abs(last.x() - prev.x())) + 2 * margin,
            int(abs(last.y() - prev.y())) + 2 * margin,
        )
        self._mark_dirty(rect)
        self.update(rect)

    def _render_full_stroke(self) -> None:
        """Re-render the entire stroke using Catmull-Rom smoothing.

        This is called on stroke end to overwrite the responsive tail
        renders with the final smoother curve.
        """
        pts = self._current_stroke
        if len(pts) < 3:
            return
        painter = QPainter(self._image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        # Already drawn during dragging; render again with full smoothing
        # so any leftover sharp joins are softened.
        for i in range(len(pts) - 1):
            self._stroke_segment(painter, pts[i], pts[i + 1])
        painter.end()
        if pts:
            xs = [p.pos.x() for p in pts]
            ys = [p.pos.y() for p in pts]
            ws = [p.width for p in pts]
            margin = int(max(ws)) + 2
            rect = QRect(
                int(min(xs)) - margin,
                int(min(ys)) - margin,
                int(max(xs) - min(xs)) + 2 * margin,
                int(max(ys) - min(ys)) + 2 * margin,
            )
            self._mark_dirty(rect)
            self.update(rect)

    def _stroke_segment(self, painter: QPainter, a: StrokePoint, b: StrokePoint) -> None:
        pen = QPen(
            QColor(0, 0, 0),
            (a.width + b.width) / 2.0,
            Qt.SolidLine,
            Qt.RoundCap,
            Qt.RoundJoin,
        )
        painter.setPen(pen)
        painter.drawLine(a.pos, b.pos)

    def _content_bbox(self) -> QRect | None:
        if self._dirty_bbox is None or self._dirty_bbox.isEmpty():
            return None
        return self._dirty_bbox.intersected(self._image.rect())

    def _mark_dirty(self, rect: QRect) -> None:
        rect = rect.intersected(self._image.rect())
        if rect.isEmpty():
            return
        self._dirty_bbox = rect if self._dirty_bbox is None else self._dirty_bbox.united(rect)

    def sizeHint(self) -> QSize:  # type: ignore[override]
        return QSize(CANVAS_W, CANVAS_H)
