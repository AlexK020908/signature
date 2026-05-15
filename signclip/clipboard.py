from __future__ import annotations

import sys

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMimeData
from PySide6.QtGui import QClipboard, QImage
from PySide6.QtWidgets import QApplication


def copy_png_to_clipboard(png_bytes: bytes) -> bool:
    """Copy a PNG (alpha-preserving) to the system clipboard.

    Strategy:
      - Load the PNG into a QImage so platform code paths can register
        the native image formats (DIB on Windows, NSPasteboard image on
        macOS, image/png on X11/Wayland).
      - Build a QMimeData carrying BOTH the QImage AND an explicit
        `image/png` mime payload with the raw PNG bytes. This is the
        format Word, Chrome, Gmail, and others prefer for alpha.
    """
    app = QApplication.instance()
    if app is None:
        return False

    img = QImage.fromData(QByteArray(png_bytes), "PNG")
    if img.isNull():
        return False

    mime = QMimeData()
    mime.setImageData(img)
    mime.setData("image/png", QByteArray(png_bytes))
    if sys.platform == "win32":
        # Word and some browsers look for the explicit "PNG" format name
        # on Windows. Qt also synthesizes CF_DIB / CF_DIBV5 from setImageData.
        mime.setData("PNG", QByteArray(png_bytes))

    clipboard = app.clipboard()
    clipboard.setMimeData(mime, QClipboard.Clipboard)
    return True


def copy_qimage_to_clipboard(image: QImage) -> bool:
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    if not image.save(buf, "PNG"):
        return False
    return copy_png_to_clipboard(bytes(buf.data()))
