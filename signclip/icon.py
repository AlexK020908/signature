from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def make_tray_icon(size: int = 64) -> QIcon:
    """Render a simple monochrome 'signature stroke' icon at runtime.

    Avoids shipping a binary asset and stays crisp on hi-DPI displays.
    Two variants are baked in (light/dark) so the menu bar looks right
    on either theme — Qt picks the right one via Mode/State.
    """
    icon = QIcon()
    for color in (QColor(40, 40, 40), QColor(230, 230, 230)):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(color, max(2.0, size / 16.0), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)

        path = QPainterPath()
        s = size
        path.moveTo(QPointF(s * 0.10, s * 0.65))
        path.cubicTo(
            QPointF(s * 0.30, s * 0.25),
            QPointF(s * 0.45, s * 0.85),
            QPointF(s * 0.65, s * 0.45),
        )
        path.cubicTo(
            QPointF(s * 0.75, s * 0.25),
            QPointF(s * 0.85, s * 0.55),
            QPointF(s * 0.92, s * 0.50),
        )
        painter.drawPath(path)
        # Baseline accent
        baseline_pen = QPen(color, max(1.5, size / 24.0))
        baseline_pen.setStyle(Qt.SolidLine)
        painter.setPen(baseline_pen)
        painter.drawLine(int(s * 0.10), int(s * 0.78), int(s * 0.92), int(s * 0.78))
        painter.end()

        if color.lightness() < 128:
            icon.addPixmap(pm, QIcon.Normal, QIcon.Off)
        else:
            icon.addPixmap(pm, QIcon.Selected, QIcon.Off)
    return icon
