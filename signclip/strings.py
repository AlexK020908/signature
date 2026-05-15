from __future__ import annotations

APP_NAME = "SignClip"
APP_TAGLINE = "Draw once. Paste anywhere."

TRAY_TOOLTIP = "SignClip — press your hotkey to paste your signature"

MENU_COPY_DEFAULT = "Copy default signature"
MENU_COPY_SUBMENU = "Copy signature"
MENU_NEW = "New signature..."
MENU_MANAGE = "Manage signatures..."
MENU_SETTINGS = "Settings"
MENU_ABOUT = "About"
MENU_QUIT = "Quit"

EDITOR_TITLE = "SignClip — New signature"
EDITOR_PROMPT_FIRST_RUN = "Draw your signature below to get started."
EDITOR_BUTTON_CLEAR = "Clear"
EDITOR_BUTTON_SAVE = "Save"
EDITOR_BUTTON_CANCEL = "Cancel"

MANAGER_TITLE = "SignClip — Manage signatures"
MANAGER_NEW = "+ New signature"
MANAGER_DEFAULT = "Default"
MANAGER_DELETE = "Delete"

SETTINGS_TITLE = "SignClip — Settings"
SETTINGS_HOTKEY = "Hotkey"
SETTINGS_HOTKEY_PROMPT = "Press a key combination..."
SETTINGS_SHOW_NOTIFICATION = "Show notification on copy"
SETTINGS_START_AT_LOGIN = "Start at login"
SETTINGS_RESET = "Reset all signatures"
SETTINGS_RESET_CONFIRM = (
    "Delete all saved signatures? This cannot be undone."
)

NOTIF_COPIED_TITLE = "Signature copied"
NOTIF_COPIED_BODY = "Paste anywhere with Ctrl+V."
NOTIF_HOTKEY_CONFLICT = "Hotkey already in use. Choose another in Settings."
NOTIF_NO_SIGNATURES = "No signatures saved yet. Open SignClip to create one."

ERROR_DECRYPT_TITLE = "Could not read signatures"
ERROR_DECRYPT_BODY = (
    "SignClip could not decrypt your saved signatures. "
    "This usually means the encryption key in your OS keyring was removed. "
    "Reset and start fresh?"
)

ERROR_KEYRING_FALLBACK = (
    "Could not access the system keyring. SignClip will store its encryption "
    "key in a protected file in your app data folder instead."
)

MACOS_ACCESSIBILITY_TITLE = "Accessibility permission required"
MACOS_ACCESSIBILITY_BODY = (
    "SignClip needs Accessibility permission to register a global hotkey. "
    "Open System Settings → Privacy & Security → Accessibility and enable SignClip."
)

ABOUT_BODY = (
    "SignClip — local, free, open source.\n"
    "Your signature never leaves this machine."
)
