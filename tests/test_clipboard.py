from __future__ import annotations

import sys

import pytest
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from signclip.clipboard import copy_png_to_clipboard, copy_qimage_to_clipboard


def _solid_alpha_png() -> bytes:
    """Build a tiny PNG with an alpha channel via Qt."""
    img = QImage(8, 8, QImage.Format_ARGB32_Premultiplied)
    img.fill(0x80FF0000)  # half-opaque red
    from PySide6.QtCore import QBuffer, QIODevice

    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    assert img.save(buf, "PNG")
    return bytes(buf.data())


# The offscreen Qt platform on Linux CI doesn't support clipboard for all
# mime types reliably, so skip there.
@pytest.mark.skipif(
    sys.platform not in ("win32", "darwin"),
    reason="Clipboard mime registration is OS-dependent; covered manually on Linux.",
)
def test_clipboard_round_trip(qt_app):
    png = _solid_alpha_png()
    assert copy_png_to_clipboard(png)
    cb = QApplication.clipboard()
    md = cb.mimeData()
    assert md.hasImage()
    # Either the explicit image/png payload OR Qt's synthesized image should round-trip.
    img = md.imageData()
    assert isinstance(img, QImage)
    assert img.hasAlphaChannel()


def test_copy_qimage_to_clipboard(qt_app):
    img = QImage(4, 4, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    assert copy_qimage_to_clipboard(img)
