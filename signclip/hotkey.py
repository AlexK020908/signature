from __future__ import annotations

import threading
from typing import Callable

try:
    from pynput import keyboard
except Exception:  # pragma: no cover - import guard for dev environments
    keyboard = None  # type: ignore[assignment]


class HotkeyError(Exception):
    """Raised when a hotkey cannot be registered."""


class HotkeyManager:
    """Wraps pynput.keyboard.GlobalHotKeys so it can be rebound at runtime.

    `on_trigger` is invoked from a background thread. The caller is responsible
    for dispatching back onto the Qt main thread (use QMetaObject.invokeMethod
    or a Qt signal).
    """

    def __init__(self, on_trigger: Callable[[], None]) -> None:
        self._on_trigger = on_trigger
        self._listener: object | None = None
        self._lock = threading.Lock()
        self._current_combo: str | None = None

    @property
    def current_combo(self) -> str | None:
        return self._current_combo

    def set_hotkey(self, combo: str) -> None:
        """Register `combo` (pynput format, e.g. '<ctrl>+<shift>+s')."""
        if keyboard is None:
            raise HotkeyError("pynput is not available.")
        with self._lock:
            self._stop_locked()
            try:
                listener = keyboard.GlobalHotKeys({combo: self._fire})
                listener.daemon = True
                listener.start()
            except Exception as exc:  # pynput raises ValueError/OSError
                raise HotkeyError(
                    f"Could not register hotkey {combo!r}: {exc}"
                ) from exc
            self._listener = listener
            self._current_combo = combo

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def _stop_locked(self) -> None:
        listener = self._listener
        self._listener = None
        self._current_combo = None
        if listener is None:
            return
        try:
            listener.stop()  # type: ignore[attr-defined]
        except Exception:
            pass

    def _fire(self) -> None:
        try:
            self._on_trigger()
        except Exception:
            # Never let an exception kill the pynput thread.
            pass
