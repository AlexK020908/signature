from __future__ import annotations

import sys
from pathlib import Path

from signclip import paths

REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_VALUE = "SignClip"


def _executable_command() -> str:
    """Best-effort command line for autostart.

    When packaged with PyInstaller, sys.executable is the SignClip binary.
    When running from source, fall back to "python -m signclip" using the
    current Python interpreter.
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" -m signclip'


def set_enabled(enabled: bool) -> bool:
    """Enable or disable launch-at-login. Returns True on success."""
    if sys.platform == "win32":
        return _set_windows(enabled)
    if sys.platform == "darwin":
        return _set_macos(enabled)
    return _set_linux(enabled)


# ---------- Windows ----------


def _set_windows(enabled: bool) -> bool:
    try:
        import winreg
    except ImportError:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE | winreg.KEY_READ) as key:
            if enabled:
                winreg.SetValueEx(key, REG_VALUE, 0, winreg.REG_SZ, _executable_command())
            else:
                try:
                    winreg.DeleteValue(key, REG_VALUE)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


# ---------- macOS ----------


def _macos_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / "com.signclip.app.plist"


def _set_macos(enabled: bool) -> bool:
    plist = _macos_plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    if enabled:
        program = sys.executable
        if getattr(sys, "frozen", False):
            args_xml = f"<string>{program}</string>"
        else:
            args_xml = (
                f"<string>{program}</string>"
                "<string>-m</string><string>signclip</string>"
            )
        plist.write_text(
            f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.signclip.app</string>
  <key>ProgramArguments</key>
  <array>
    {args_xml}
  </array>
  <key>RunAtLoad</key><true/>
</dict>
</plist>
""",
            encoding="utf-8",
        )
        return True
    if plist.exists():
        try:
            plist.unlink()
        except OSError:
            return False
    return True


# ---------- Linux ----------


def _linux_desktop_path() -> Path:
    base = Path.home() / ".config" / "autostart"
    return base / "signclip.desktop"


def _set_linux(enabled: bool) -> bool:
    desktop = _linux_desktop_path()
    desktop.parent.mkdir(parents=True, exist_ok=True)
    if enabled:
        exec_cmd = _executable_command().strip('"')
        desktop.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=SignClip\n"
            f"Exec={exec_cmd}\n"
            "X-GNOME-Autostart-enabled=true\n",
            encoding="utf-8",
        )
        return True
    if desktop.exists():
        try:
            desktop.unlink()
        except OSError:
            return False
    return True
