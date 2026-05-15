from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QImage, QMouseEvent

from signclip.canvas import CANVAS_H, CANVAS_W, SignatureCanvas


def _press(canvas: SignatureCanvas, x: float, y: float) -> None:
    pos = QPointF(x, y)
    event = QMouseEvent(QMouseEvent.MouseButtonPress, pos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    canvas.mousePressEvent(event)


def _move(canvas: SignatureCanvas, x: float, y: float) -> None:
    pos = QPointF(x, y)
    event = QMouseEvent(QMouseEvent.MouseMove, pos, Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
    canvas.mouseMoveEvent(event)


def _release(canvas: SignatureCanvas, x: float, y: float) -> None:
    pos = QPointF(x, y)
    event = QMouseEvent(QMouseEvent.MouseButtonRelease, pos, Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    canvas.mouseReleaseEvent(event)


def test_empty_canvas_returns_none(qt_app):
    c = SignatureCanvas()
    assert c.is_empty()
    assert c.export_png() is None


def test_draw_and_export_png(qt_app):
    c = SignatureCanvas()
    _press(c, 100, 200)
    for x in range(105, 405, 5):
        _move(c, float(x), 200.0 + ((x % 20) - 10) * 0.5)
    _release(c, 400, 200)

    assert not c.is_empty()
    data = c.export_png()
    assert data is not None
    # Should be a real PNG with transparency-capable header.
    assert data.startswith(b"\x89PNG\r\n\x1a\n")

    loaded = QImage.fromData(data, "PNG")
    assert not loaded.isNull()
    # Should be trimmed: width/height much smaller than the full canvas.
    assert loaded.width() < CANVAS_W
    assert loaded.height() < CANVAS_H
    assert loaded.hasAlphaChannel()


def test_clear_resets_state(qt_app):
    c = SignatureCanvas()
    _press(c, 50, 50)
    _move(c, 100, 100)
    _release(c, 100, 100)
    assert not c.is_empty()
    c.clear()
    assert c.is_empty()
    assert c.export_png() is None
