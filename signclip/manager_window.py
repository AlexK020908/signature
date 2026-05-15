from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from signclip.storage import Signature, SignatureStore
from signclip.strings import (
    APP_NAME,
    MANAGER_DEFAULT,
    MANAGER_DELETE,
    MANAGER_NEW,
    MANAGER_TITLE,
)

THUMB_W = 240
THUMB_H = 80


def _checker_pixmap(width: int, height: int) -> QPixmap:
    """Render an image preview against a checkered background so users can
    see transparency. The signature image itself stays unmodified."""
    pm = QPixmap(width, height)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    light = QColor(240, 240, 240)
    dark = QColor(210, 210, 210)
    tile = 8
    for y in range(0, height, tile):
        for x in range(0, width, tile):
            painter.fillRect(
                x, y, tile, tile,
                light if ((x // tile + y // tile) % 2 == 0) else dark,
            )
    painter.end()
    return pm


def render_thumbnail(png_bytes: bytes, width: int = THUMB_W, height: int = THUMB_H) -> QPixmap:
    img = QImage.fromData(png_bytes, "PNG")
    bg = _checker_pixmap(width, height)
    if img.isNull():
        return bg
    scaled = img.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    painter = QPainter(bg)
    x = (width - scaled.width()) // 2
    y = (height - scaled.height()) // 2
    painter.drawImage(x, y, scaled)
    painter.end()
    return bg


class SignatureRow(QWidget):
    request_delete = Signal(str)
    name_changed = Signal(str, str)  # id, new name
    set_default = Signal(str)

    def __init__(self, sig: Signature, *, is_default: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sig_id = sig.id

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        thumb_label = QLabel()
        thumb_label.setPixmap(render_thumbnail(sig.png_bytes))
        thumb_label.setFixedSize(THUMB_W, THUMB_H)
        layout.addWidget(thumb_label)

        center = QVBoxLayout()
        self._name_field = QLineEdit(sig.name)
        self._name_field.setMaxLength(60)
        self._name_field.editingFinished.connect(self._on_name_edit)
        center.addWidget(self._name_field)

        created = QLabel(sig.created_at)
        created.setStyleSheet("color: #888; font-size: 11px;")
        center.addWidget(created)
        layout.addLayout(center, 1)

        self._default_radio = QRadioButton(MANAGER_DEFAULT)
        self._default_radio.setChecked(is_default)
        self._default_radio.toggled.connect(self._on_default_toggle)
        layout.addWidget(self._default_radio)

        delete_btn = QPushButton(MANAGER_DELETE)
        delete_btn.clicked.connect(lambda: self.request_delete.emit(self._sig_id))
        layout.addWidget(delete_btn)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    @property
    def default_radio(self) -> QRadioButton:
        return self._default_radio

    @property
    def signature_id(self) -> str:
        return self._sig_id

    def _on_name_edit(self) -> None:
        new = self._name_field.text().strip()
        if new:
            self.name_changed.emit(self._sig_id, new)

    def _on_default_toggle(self, checked: bool) -> None:
        if checked:
            self.set_default.emit(self._sig_id)


class ManagerWindow(QDialog):
    """List of saved signatures with edit/delete/default-set controls."""

    request_new = Signal()

    def __init__(
        self,
        store: SignatureStore,
        *,
        parent: QWidget | None = None,
        on_persist: Callable[[SignatureStore], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._on_persist = on_persist
        self.setWindowTitle(MANAGER_TITLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        top_row = QHBoxLayout()
        top_row.addStretch(1)
        self._new_btn = QPushButton(MANAGER_NEW)
        self._new_btn.clicked.connect(self.request_new.emit)
        top_row.addWidget(self._new_btn)
        layout.addLayout(top_row)

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.NoSelection)
        self._list.setIconSize(QSize(THUMB_W, THUMB_H))
        layout.addWidget(self._list, 1)

        self._default_group = QButtonGroup(self)
        self._default_group.setExclusive(True)

        self.refresh()
        self.resize(640, 480)

    def refresh(self) -> None:
        self._list.clear()
        # Re-create group to avoid stale references.
        for btn in list(self._default_group.buttons()):
            self._default_group.removeButton(btn)

        if not self._store.signatures:
            placeholder = QListWidgetItem("No signatures yet. Click \"+ New signature\" to draw one.")
            placeholder.setFlags(Qt.NoItemFlags)
            self._list.addItem(placeholder)
            return

        for sig in self._store.signatures:
            is_default = sig.id == self._store.default_id
            row = SignatureRow(sig, is_default=is_default, parent=self._list)
            row.request_delete.connect(self._on_delete)
            row.name_changed.connect(self._on_rename)
            row.set_default.connect(self._on_set_default)

            item = QListWidgetItem()
            item.setSizeHint(row.sizeHint() + QSize(0, 8))
            self._list.addItem(item)
            self._list.setItemWidget(item, row)
            self._default_group.addButton(row.default_radio)

    # ---- handlers ----

    def _persist(self) -> None:
        if self._on_persist is not None:
            self._on_persist(self._store)

    def _on_delete(self, sig_id: str) -> None:
        sig = self._store.find(sig_id)
        if sig is None:
            return
        confirm = QMessageBox.question(
            self,
            APP_NAME,
            f"Delete \"{sig.name}\"? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.Cancel,
        )
        if confirm != QMessageBox.Yes:
            return
        self._store.delete(sig_id)
        self._persist()
        self.refresh()

    def _on_rename(self, sig_id: str, new_name: str) -> None:
        self._store.rename(sig_id, new_name)
        self._persist()

    def _on_set_default(self, sig_id: str) -> None:
        self._store.set_default(sig_id)
        self._persist()
