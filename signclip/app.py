from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from signclip import autostart, settings, storage
from signclip.clipboard import copy_png_to_clipboard
from signclip.editor_window import EditorWindow
from signclip.hotkey import HotkeyError, HotkeyManager
from signclip.icon import make_tray_icon
from signclip.manager_window import ManagerWindow
from signclip.settings_window import SettingsWindow
from signclip.storage import SignatureStore
from signclip.strings import (
    ABOUT_BODY,
    APP_NAME,
    ERROR_DECRYPT_BODY,
    ERROR_DECRYPT_TITLE,
    ERROR_KEYRING_FALLBACK,
    MACOS_ACCESSIBILITY_BODY,
    MACOS_ACCESSIBILITY_TITLE,
    NOTIF_COPIED_BODY,
    NOTIF_COPIED_TITLE,
    NOTIF_HOTKEY_CONFLICT,
    NOTIF_NO_SIGNATURES,
)
from signclip.tray import TrayController


class SignClipApp(QObject):
    """Top-level controller. Holds the QApplication and all UI singletons."""

    _hotkey_triggered = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._qt_app = QApplication.instance() or QApplication(sys.argv)
        self._qt_app.setApplicationName(APP_NAME)
        self._qt_app.setQuitOnLastWindowClosed(False)

        # System tray must be available.
        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.critical(
                None,
                APP_NAME,
                "Your system does not appear to support a system tray. "
                "SignClip needs the tray to run.",
            )
            raise SystemExit(1)

        self._settings = settings.load()
        self._store = self._load_store_with_dialog()
        self._notified_keyring_fallback = False

        self._tray = TrayController(make_tray_icon(), parent=self)
        self._tray.set_store(self._store)
        self._wire_tray()

        self._editor: EditorWindow | None = None
        self._manager: ManagerWindow | None = None
        self._settings_window: SettingsWindow | None = None

        self._hotkey = HotkeyManager(on_trigger=self._hotkey_triggered.emit)
        self._hotkey_triggered.connect(
            self._on_hotkey, type=Qt.QueuedConnection
        )
        self._register_hotkey(initial=True)

        # First-run flow: open the editor if there are no signatures yet.
        if len(self._store) == 0:
            QTimer.singleShot(0, lambda: self.open_editor(first_run=True))

    # ---- lifecycle ----

    def run(self) -> int:
        self._qt_app.aboutToQuit.connect(self._cleanup)
        return int(self._qt_app.exec())

    def _cleanup(self) -> None:
        self._hotkey.stop()
        self._tray.hide()

    # ---- storage load / persist ----

    def _on_keyring_fallback(self) -> None:
        if self._notified_keyring_fallback:
            return
        self._notified_keyring_fallback = True
        QTimer.singleShot(
            0,
            lambda: QMessageBox.warning(None, APP_NAME, ERROR_KEYRING_FALLBACK),
        )

    def _load_store_with_dialog(self) -> SignatureStore:
        try:
            return storage.load(on_fallback=self._on_keyring_fallback)
        except storage.DecryptError:
            reply = QMessageBox.question(
                None,
                ERROR_DECRYPT_TITLE,
                ERROR_DECRYPT_BODY,
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                storage.reset_all()
                return SignatureStore()
            raise SystemExit(1)

    def _persist_store(self, store: SignatureStore | None = None) -> None:
        target = store or self._store
        storage.save(target, on_fallback=self._on_keyring_fallback)
        self._tray.rebuild_menu()

    def _persist_settings(self, new_settings: settings.Settings) -> None:
        old_hotkey = self._settings.hotkey
        old_autostart = self._settings.start_at_login
        self._settings = new_settings
        settings.save(new_settings)
        if new_settings.hotkey != old_hotkey:
            self._register_hotkey(initial=False)
        if new_settings.start_at_login != old_autostart:
            autostart.set_enabled(new_settings.start_at_login)

    # ---- hotkey ----

    def _register_hotkey(self, *, initial: bool) -> None:
        try:
            self._hotkey.set_hotkey(self._settings.hotkey)
        except HotkeyError:
            if sys.platform == "darwin" and initial:
                QMessageBox.information(
                    None,
                    MACOS_ACCESSIBILITY_TITLE,
                    MACOS_ACCESSIBILITY_BODY,
                )
            self._tray.notify(NOTIF_HOTKEY_CONFLICT)

    def _on_hotkey(self) -> None:
        self._copy_default()

    # ---- tray wiring ----

    def _wire_tray(self) -> None:
        self._tray.copy_default_requested.connect(self._copy_default)
        self._tray.copy_signature_requested.connect(self._copy_signature)
        self._tray.open_editor_requested.connect(lambda: self.open_editor(first_run=False))
        self._tray.open_manager_requested.connect(self.open_manager)
        self._tray.open_settings_requested.connect(self.open_settings)
        self._tray.show_about_requested.connect(self._show_about)
        self._tray.quit_requested.connect(self._qt_app.quit)

    # ---- actions ----

    def _copy_default(self) -> None:
        sig = self._store.default()
        if sig is None:
            self._tray.notify(NOTIF_NO_SIGNATURES)
            return
        self._copy_bytes(sig.png_bytes)

    def _copy_signature(self, sig_id: str) -> None:
        sig = self._store.find(sig_id)
        if sig is None:
            return
        self._copy_bytes(sig.png_bytes)

    def _copy_bytes(self, png: bytes) -> None:
        if copy_png_to_clipboard(png):
            if self._settings.show_notification:
                self._tray.notify(NOTIF_COPIED_BODY, title=NOTIF_COPIED_TITLE)

    # ---- windows ----

    def open_editor(self, *, first_run: bool = False) -> None:
        if self._editor is not None and self._editor.isVisible():
            self._editor.raise_()
            self._editor.activateWindow()
            return
        self._editor = EditorWindow(
            self._store,
            first_run=first_run,
            on_persist=self._persist_store,
        )
        self._editor.signature_saved.connect(self._on_signature_saved)
        self._editor.finished.connect(self._on_editor_finished)
        self._editor.show()
        self._editor.raise_()
        self._editor.activateWindow()

    def _on_editor_finished(self, _result: int) -> None:
        self._editor = None
        if self._manager is not None and self._manager.isVisible():
            self._manager.refresh()

    def _on_signature_saved(self, _sig_id: str) -> None:
        self._tray.rebuild_menu()
        self._tray.notify(
            "Signature saved. Press your hotkey anywhere to paste it.",
            title=APP_NAME,
        )

    def open_manager(self) -> None:
        if self._manager is not None and self._manager.isVisible():
            self._manager.raise_()
            self._manager.activateWindow()
            return
        self._manager = ManagerWindow(
            self._store,
            on_persist=self._persist_store,
        )
        self._manager.request_new.connect(lambda: self.open_editor(first_run=False))
        self._manager.finished.connect(self._on_manager_finished)
        self._manager.show()

    def _on_manager_finished(self, _result: int) -> None:
        self._manager = None

    def open_settings(self) -> None:
        if self._settings_window is not None and self._settings_window.isVisible():
            self._settings_window.raise_()
            self._settings_window.activateWindow()
            return
        self._settings_window = SettingsWindow(
            self._settings,
            on_persist=self._persist_settings,
        )
        self._settings_window.reset_requested.connect(self._reset_all)
        self._settings_window.finished.connect(self._on_settings_finished)
        self._settings_window.show()

    def _on_settings_finished(self, _result: int) -> None:
        self._settings_window = None

    def _reset_all(self) -> None:
        storage.reset_all()
        self._store = SignatureStore()
        self._tray.set_store(self._store)
        if self._manager is not None and self._manager.isVisible():
            self._manager.refresh()

    def _show_about(self) -> None:
        QMessageBox.information(None, APP_NAME, ABOUT_BODY)


def main(argv: Optional[list[str]] = None) -> int:
    if argv is not None:
        sys.argv = [sys.argv[0], *argv]
    app = SignClipApp()
    return app.run()
