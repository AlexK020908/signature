from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
WORK = ROOT / "build" / "_pyinstaller"


def main() -> int:
    entrypoint = ROOT / "signclip" / "__main__.py"

    # Prefer `python -m PyInstaller` so the build works regardless of whether
    # the pyinstaller console script is on PATH (common inside venvs on Windows).
    args = [
        sys.executable, "-m", "PyInstaller",
        str(entrypoint),
        "--name", "SignClip",
        "--onefile",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--distpath", str(DIST),
        "--workpath", str(WORK),
        "--specpath", str(WORK),
    ]

    if sys.platform == "darwin":
        args += ["--osx-bundle-identifier", "com.signclip.app"]

    print("Running:", " ".join(args))
    completed = subprocess.run(args, cwd=ROOT)
    if completed.returncode != 0:
        return completed.returncode

    # macOS LSUIElement (tray-only, no dock icon)
    if sys.platform == "darwin":
        plist = DIST / "SignClip.app" / "Contents" / "Info.plist"
        if plist.exists():
            text = plist.read_text(encoding="utf-8")
            if "LSUIElement" not in text:
                text = text.replace(
                    "</dict>",
                    "    <key>LSUIElement</key>\n    <true/>\n</dict>",
                    1,
                )
                plist.write_text(text, encoding="utf-8")
                print("Patched Info.plist with LSUIElement = true")

    # Linux desktop entry (for `Start at login` users to optionally install)
    if sys.platform.startswith("linux"):
        desktop = DIST / "signclip.desktop"
        desktop.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=SignClip\n"
            "Exec={}/SignClip\n".format(DIST) +
            "Icon=signclip\n"
            "Comment=Local signature clipboard\n"
            "Categories=Utility;\n",
            encoding="utf-8",
        )
        print(f"Wrote {desktop}")

    print(f"Build complete. Output: {DIST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
