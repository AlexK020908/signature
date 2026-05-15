from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from signclip import storage
from signclip.canvas import SignatureCanvas
from signclip.storage import MAX_SIGNATURES, Signature, SignatureStore
from signclip.strings import (
    APP_NAME,
    EDITOR_BUTTON_CANCEL,
    EDITOR_BUTTON_CLEAR,
    EDITOR_BUTTON_SAVE,
    EDITOR_PROMPT_FIRST_RUN,
    EDITOR_TITLE,
)


class EditorWindow(QDialog):
    """Modal-ish editor for drawing and saving a signature.

    Emits `signature_saved` after a successful save.
    """

    signature_saved = Signal(str)  # signature id

    def __init__(
        self,
        store: SignatureStore,
        *,
        parent: QWidget | None = None,
        first_run: bool = False,
        on_persist: Callable[[SignatureStore], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._on_persist = on_persist
        self.setWindowTitle(EDITOR_TITLE)
        # Allow the editor to be closed independently of the tray.
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinimizeButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        prompt = QLabel(
            EDITOR_PROMPT_FIRST_RUN if first_run else "Draw your signature below."
        )
        prompt.setStyleSheet("color: #444; font-size: 14px;")
        layout.addWidget(prompt)

        self._canvas = SignatureCanvas(self)
        canvas_row = QHBoxLayout()
        canvas_row.addStretch(1)
        canvas_row.addWidget(self._canvas)
        canvas_row.addStretch(1)
        layout.addLayout(canvas_row)

        # Name field
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self._name_field = QLineEdit()
        self._name_field.setPlaceholderText("My signature")
        self._name_field.setMaxLength(60)
        name_row.addWidget(self._name_field, 1)
        layout.addLayout(name_row)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._clear_btn = QPushButton(EDITOR_BUTTON_CLEAR)
        self._cancel_btn = QPushButton(EDITOR_BUTTON_CANCEL)
        self._save_btn = QPushButton(EDITOR_BUTTON_SAVE)
        self._save_btn.setDefault(True)
        btn_row.addWidget(self._clear_btn)
        btn_row.addWidget(self._cancel_btn)
        btn_row.addWidget(self._save_btn)
        layout.addLayout(btn_row)

        self._clear_btn.clicked.connect(self._on_clear)
        self._cancel_btn.clicked.connect(self.reject)
        self._save_btn.clicked.connect(self._on_save)

        self.adjustSize()
        self.setMinimumSize(self.size())

    # ---- handlers ----

    def _on_clear(self) -> None:
        self._canvas.clear()

    def _on_save(self) -> None:
        if self._canvas.is_empty():
            QMessageBox.information(
                self,
                APP_NAME,
                "Draw something first, then click Save.",
            )
            return
        if len(self._store) >= MAX_SIGNATURES:
            QMessageBox.warning(
                self,
                APP_NAME,
                f"You can keep up to {MAX_SIGNATURES} signatures. "
                "Delete one in Manage signatures, then try again.",
            )
            return
        png = self._canvas.export_png()
        if png is None:
            QMessageBox.warning(self, APP_NAME, "Could not export the signature.")
            return

        name = self._name_field.text().strip()
        if not name:
            name, ok = QInputDialog.getText(
                self,
                APP_NAME,
                "Give this signature a name:",
                text="My signature",
            )
            if not ok:
                return
            name = name.strip() or "My signature"

        sig = Signature.create(name=name, png_bytes=png)
        self._store.add(sig)
        if self._on_persist is not None:
            try:
                self._on_persist(self._store)
            except storage.StorageError as exc:
                # Roll back the in-memory add so we don't lie to the user.
                self._store.delete(sig.id)
                QMessageBox.critical(self, APP_NAME, str(exc))
                return
        self.signature_saved.emit(sig.id)
        self.accept()

    # ---- lifecycle ----

    def closeEvent(self, event: QCloseEvent) -> None:
        # Closing the editor window does NOT quit the app — the tray remains.
        super().closeEvent(event)
