from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from signclip.storage import SignatureStore
from signclip.strings import (
    APP_NAME,
    MENU_ABOUT,
    MENU_COPY_DEFAULT,
    MENU_COPY_SUBMENU,
    MENU_MANAGE,
    MENU_NEW,
    MENU_QUIT,
    MENU_SETTINGS,
    TRAY_TOOLTIP,
)


class TrayController(QObject):
    """Owns the QSystemTrayIcon and exposes Qt signals for menu actions."""

    copy_default_requested = Signal()
    copy_signature_requested = Signal(str)  # signature id
    open_editor_requested = Signal()
    open_manager_requested = Signal()
    open_settings_requested = Signal()
    show_about_requested = Signal()
    quit_requested = Signal()

    def __init__(self, icon: QIcon, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._tray = QSystemTrayIcon(icon, parent)
        self._tray.setToolTip(TRAY_TOOLTIP)
        self._tray.activated.connect(self._on_activated)

        self._menu = QMenu()
        self._tray.setContextMenu(self._menu)
        self._tray.show()

        # Cached state for rebuild
        self._store: SignatureStore | None = None

    # ---- public API ----

    def set_store(self, store: SignatureStore) -> None:
        self._store = store
        self.rebuild_menu()

    def rebuild_menu(self) -> None:
        self._menu.clear()
        store = self._store

        copy_default = QAction(MENU_COPY_DEFAULT, self._menu)
        copy_default.triggered.connect(self.copy_default_requested.emit)
        copy_default.setEnabled(bool(store and len(store) > 0))
        self._menu.addAction(copy_default)

        if store and len(store) > 1:
            submenu = self._menu.addMenu(MENU_COPY_SUBMENU)
            for sig in store.iter():
                act = QAction(sig.name or "(unnamed)", submenu)
                sig_id = sig.id
                act.triggered.connect(lambda _checked=False, _id=sig_id: self.copy_signature_requested.emit(_id))
                submenu.addAction(act)

        self._menu.addSeparator()

        new_act = QAction(MENU_NEW, self._menu)
        new_act.triggered.connect(self.open_editor_requested.emit)
        self._menu.addAction(new_act)

        manage_act = QAction(MENU_MANAGE, self._menu)
        manage_act.triggered.connect(self.open_manager_requested.emit)
        self._menu.addAction(manage_act)

        settings_act = QAction(MENU_SETTINGS, self._menu)
        settings_act.triggered.connect(self.open_settings_requested.emit)
        self._menu.addAction(settings_act)

        self._menu.addSeparator()

        about_act = QAction(MENU_ABOUT, self._menu)
        about_act.triggered.connect(self.show_about_requested.emit)
        self._menu.addAction(about_act)

        quit_act = QAction(MENU_QUIT, self._menu)
        quit_act.triggered.connect(self.quit_requested.emit)
        self._menu.addAction(quit_act)

    def notify(self, body: str, *, title: str = APP_NAME, ms: int = 2000) -> None:
        if QSystemTrayIcon.supportsMessages():
            self._tray.showMessage(title, body, QSystemTrayIcon.Information, ms)

    def hide(self) -> None:
        self._tray.hide()

    # ---- internals ----

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # Left-click on the tray icon copies the default signature.
        if reason == QSystemTrayIcon.Trigger:
            self.copy_default_requested.emit()
