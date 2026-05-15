from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from signclip import __version__, settings
from signclip.strings import (
    APP_NAME,
    SETTINGS_HOTKEY,
    SETTINGS_HOTKEY_PROMPT,
    SETTINGS_RESET,
    SETTINGS_RESET_CONFIRM,
    SETTINGS_SHOW_NOTIFICATION,
    SETTINGS_START_AT_LOGIN,
    SETTINGS_TITLE,
)


_QT_TO_PYNPUT_MODIFIER = {
    Qt.ControlModifier: "<ctrl>",
    Qt.ShiftModifier: "<shift>",
    Qt.AltModifier: "<alt>",
    Qt.MetaModifier: "<cmd>",
}

# Map Qt special keys to pynput names. Anything not listed falls back to text().
_QT_SPECIAL_KEYS = {
    Qt.Key_Space: "<space>",
    Qt.Key_Return: "<enter>",
    Qt.Key_Enter: "<enter>",
    Qt.Key_Tab: "<tab>",
    Qt.Key_Backspace: "<backspace>",
    Qt.Key_Delete: "<delete>",
    Qt.Key_Escape: "<esc>",
    Qt.Key_F1: "<f1>",
    Qt.Key_F2: "<f2>",
    Qt.Key_F3: "<f3>",
    Qt.Key_F4: "<f4>",
    Qt.Key_F5: "<f5>",
    Qt.Key_F6: "<f6>",
    Qt.Key_F7: "<f7>",
    Qt.Key_F8: "<f8>",
    Qt.Key_F9: "<f9>",
    Qt.Key_F10: "<f10>",
    Qt.Key_F11: "<f11>",
    Qt.Key_F12: "<f12>",
}

_MODIFIER_KEYS = {Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta}


class HotkeyCaptureField(QLineEdit):
    """A line-edit that captures the next key-combo the user presses."""

    combo_captured = Signal(str)  # pynput-format combo

    def __init__(self, current: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText(SETTINGS_HOTKEY_PROMPT)
        self._combo = current
        self.setText(current)

    def focusInEvent(self, event: QEvent) -> None:  # type: ignore[override]
        super().focusInEvent(event)
        self.setPlaceholderText("Press a combination...")
        self.setText("")

    def focusOutEvent(self, event: QEvent) -> None:  # type: ignore[override]
        super().focusOutEvent(event)
        if not self.text():
            self.setText(self._combo)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if event.key() in _MODIFIER_KEYS:
            return
        parts: list[str] = []
        mods = event.modifiers()
        for mod, name in _QT_TO_PYNPUT_MODIFIER.items():
            if mods & mod:
                parts.append(name)
        if event.key() in _QT_SPECIAL_KEYS:
            parts.append(_QT_SPECIAL_KEYS[event.key()])
        else:
            text = event.text().lower()
            if not text or not text.isprintable():
                return
            parts.append(text)
        combo = "+".join(parts)
        self._combo = combo
        self.setText(combo)
        self.combo_captured.emit(combo)


class SettingsWindow(QDialog):
    settings_changed = Signal(object)  # emits Settings
    reset_requested = Signal()

    def __init__(
        self,
        current: settings.Settings,
        *,
        parent: QWidget | None = None,
        on_persist: Callable[[settings.Settings], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings.Settings(
            hotkey=current.hotkey,
            show_notification=current.show_notification,
            start_at_login=current.start_at_login,
        )
        self._on_persist = on_persist
        self.setWindowTitle(SETTINGS_TITLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Hotkey
        layout.addWidget(QLabel(SETTINGS_HOTKEY))
        self._hotkey_field = HotkeyCaptureField(current.hotkey)
        self._hotkey_field.combo_captured.connect(self._on_hotkey)
        layout.addWidget(self._hotkey_field)

        # Toggles
        self._notif_cb = QCheckBox(SETTINGS_SHOW_NOTIFICATION)
        self._notif_cb.setChecked(current.show_notification)
        self._notif_cb.toggled.connect(self._on_notif)
        layout.addWidget(self._notif_cb)

        self._autostart_cb = QCheckBox(SETTINGS_START_AT_LOGIN)
        self._autostart_cb.setChecked(current.start_at_login)
        self._autostart_cb.toggled.connect(self._on_autostart)
        layout.addWidget(self._autostart_cb)

        # Danger zone
        reset_btn = QPushButton(SETTINGS_RESET)
        reset_btn.clicked.connect(self._on_reset)
        layout.addWidget(reset_btn)

        layout.addStretch(1)

        footer = QLabel(f"{APP_NAME} v{__version__} — local, free, open source.")
        footer.setStyleSheet("color: #888; font-size: 11px;")
        footer.setAlignment(Qt.AlignCenter)
        layout.addWidget(footer)

        # Close button
        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        self.setMinimumWidth(420)

    # ---- handlers ----

    def _on_hotkey(self, combo: str) -> None:
        self._settings.hotkey = combo
        self._persist()

    def _on_notif(self, checked: bool) -> None:
        self._settings.show_notification = checked
        self._persist()

    def _on_autostart(self, checked: bool) -> None:
        self._settings.start_at_login = checked
        self._persist()

    def _on_reset(self) -> None:
        confirm = QMessageBox.question(
            self,
            APP_NAME,
            SETTINGS_RESET_CONFIRM,
            QMessageBox.Yes | QMessageBox.Cancel,
        )
        if confirm == QMessageBox.Yes:
            self.reset_requested.emit()

    def _persist(self) -> None:
        if self._on_persist is not None:
            self._on_persist(self._settings)
        self.settings_changed.emit(self._settings)
