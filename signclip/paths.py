from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "SignClip"
APP_DIR_NAME_LINUX = "signclip"


def app_data_dir() -> Path:
    """Return the platform-appropriate per-user app data directory.

    Windows: %APPDATA%\\SignClip
    macOS:   ~/Library/Application Support/SignClip
    Linux:   ~/.config/signclip  (honors $XDG_CONFIG_HOME)
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Roaming"
        path = root / APP_DIR_NAME
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    else:
        base = os.environ.get("XDG_CONFIG_HOME")
        root = Path(base) if base else Path.home() / ".config"
        path = root / APP_DIR_NAME_LINUX
    path.mkdir(parents=True, exist_ok=True)
    return path


def signatures_file() -> Path:
    return app_data_dir() / "signatures.dat"


def keyfile_fallback() -> Path:
    return app_data_dir() / "signclip.key"


def settings_file() -> Path:
    return app_data_dir() / "settings.json"


def log_file() -> Path:
    return app_data_dir() / "signclip.log"
