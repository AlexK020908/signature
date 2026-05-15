"""Build distributable packages for SignClip.

Produces:
  dist/SignClip.exe            (already built by build.py)
  dist/SignClip-Portable.zip   portable zip with EXE + README + LICENSE
  dist/SignClip-Setup.exe      Inno Setup installer (if ISCC.exe is installed)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
EXE = DIST / "SignClip.exe"


def build_portable_zip() -> Path:
    out = DIST / "SignClip-Portable.zip"
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.write(EXE, "SignClip/SignClip.exe")
        zf.write(ROOT / "README.md", "SignClip/README.md")
        zf.write(ROOT / "LICENSE", "SignClip/LICENSE.txt")
        zf.writestr(
            "SignClip/Run SignClip.txt",
            "Double-click SignClip.exe to launch.\n"
            "It will appear in your system tray (near the clock).\n"
            "Press Ctrl+Shift+S anywhere, then Ctrl+V to paste your signature.\n",
        )
    return out


def find_iscc() -> Path | None:
    """Locate Inno Setup's command-line compiler."""
    env = os.environ.get("ISCC")
    if env and Path(env).exists():
        return Path(env)
    candidates = [
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    ]
    found = shutil.which("ISCC")
    if found:
        candidates.insert(0, Path(found))
    for c in candidates:
        if c.exists():
            return c
    return None


def build_installer() -> Path | None:
    iscc = find_iscc()
    if iscc is None:
        print(
            "Inno Setup not found — skipping SignClip-Setup.exe.\n"
            "Install from https://jrsoftware.org/isinfo.php (free) and re-run.\n"
        )
        return None
    script = ROOT / "build" / "installer.iss"
    print(f"Compiling installer with {iscc}")
    completed = subprocess.run([str(iscc), str(script)], cwd=ROOT)
    if completed.returncode != 0:
        print(f"ISCC failed with exit code {completed.returncode}")
        return None
    out = DIST / "SignClip-Setup.exe"
    return out if out.exists() else None


def main() -> int:
    if not EXE.exists():
        print(f"{EXE} not found. Run build/build.py first.")
        return 1

    portable = build_portable_zip()
    size_mb = portable.stat().st_size / (1024 * 1024)
    print(f"Wrote {portable} ({size_mb:.1f} MB)")

    installer = build_installer()
    if installer:
        size_mb = installer.stat().st_size / (1024 * 1024)
        print(f"Wrote {installer} ({size_mb:.1f} MB)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
