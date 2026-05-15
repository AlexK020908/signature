from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass

from signclip import paths


def default_hotkey() -> str:
    if sys.platform == "darwin":
        return "<cmd>+<shift>+s"
    return "<ctrl>+<shift>+s"


@dataclass
class Settings:
    hotkey: str = ""
    show_notification: bool = True
    start_at_login: bool = False

    def __post_init__(self) -> None:
        if not self.hotkey:
            self.hotkey = default_hotkey()


def load() -> Settings:
    path = paths.settings_file()
    if not path.exists():
        return Settings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Settings()
    return Settings(
        hotkey=data.get("hotkey", default_hotkey()),
        show_notification=bool(data.get("show_notification", True)),
        start_at_login=bool(data.get("start_at_login", False)),
    )


def save(settings: Settings) -> None:
    path = paths.settings_file()
    path.write_text(
        json.dumps(asdict(settings), indent=2),
        encoding="utf-8",
    )
