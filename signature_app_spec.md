# SignClip — Local Signature Clipboard App

A free, local-only desktop app that lets users draw a signature once and paste it as a transparent PNG anywhere with a global hotkey. No accounts, no uploads, no internet required.

---

## 1. Product Principles

These are non-negotiable. Every design decision must respect them.

1. **Local only.** The app never makes a network request. Period. No telemetry, no update checks, no analytics.
2. **Signature never touches the network.** Stored encrypted on disk in the user's app data folder.
3. **No accounts.** No sign-up, no login, no email required.
4. **Always free.** No premium tier, no upsell, no nags.
5. **True transparent PNG.** Drawn on a transparent canvas from the start — never background-removed after the fact, so no halos or anti-aliasing artifacts.
6. **Frictionless paste.** From hotkey to pasted signature: under one second.

---

## 2. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | User requirement |
| GUI framework | **PySide6** (Qt for Python, LGPL) | Best cross-platform GUI, native system tray, excellent clipboard with image support, mature drawing APIs. LGPL license means no commercial licensing issues for a free app. |
| Global hotkey | **pynput** | Cross-platform global hotkey listener that works while app is minimized to tray |
| Encryption | **cryptography** (Fernet) | Standard library for symmetric encryption of stored signature |
| Packaging | **PyInstaller** | Single-file .exe / .app distribution |
| Image format | PNG with alpha channel via Qt's `QImage` | Native transparency support, universally pasteable |

**Do not use:** Tkinter (no proper system tray), PyQt (GPL — would force open-sourcing of any commercial fork), web frameworks (violates the "local only" principle).

---

## 3. Project Structure

```
signclip/
├── README.md
├── requirements.txt
├── pyproject.toml
├── signclip/
│   ├── __init__.py
│   ├── __main__.py              # Entry point: `python -m signclip`
│   ├── app.py                   # QApplication setup, tray icon, lifecycle
│   ├── tray.py                  # System tray icon and menu
│   ├── canvas.py                # Signature drawing widget (transparent canvas)
│   ├── editor_window.py         # Window that hosts the canvas + Save/Clear buttons
│   ├── manager_window.py        # List of saved signatures, set default, delete
│   ├── storage.py               # Encrypted load/save of signatures to disk
│   ├── clipboard.py             # Copy PNG to clipboard with alpha
│   ├── hotkey.py                # Global hotkey registration via pynput
│   ├── paths.py                 # Cross-platform app data directory
│   └── assets/
│       └── icon.png             # Tray icon
├── build/
│   └── build.py                 # PyInstaller build script
└── tests/
    ├── test_storage.py
    ├── test_canvas.py
    └── test_clipboard.py
```

---

## 4. Feature Specification

### 4.1 Drawing Canvas

**What it does:** lets the user draw a signature with mouse, trackpad, or pen tablet.

**Requirements:**
- Canvas dimensions: **1200 × 400 pixels** (wide aspect, mimics a signature line on paper).
- Background: **fully transparent** (`QImage.Format_ARGB32_Premultiplied`). Display a light grid or guide line *as a separate overlay* — never paint it into the saved image.
- Pen: black, **anti-aliased**, variable stroke width based on cursor speed (faster = thinner, slower = thicker — emulates ink). Default width 3px, range 1.5–5px.
- Input: handle `mousePressEvent`, `mouseMoveEvent`, `mouseReleaseEvent`. Use `QPainter` with `RenderHint.Antialiasing` and `RenderHint.SmoothPixmapTransform`.
- Smoothing: collect raw points, then render strokes as **Catmull-Rom or quadratic Bezier splines** rather than straight line segments. Straight `lineTo` produces visibly jagged signatures.
- **Pressure sensitivity:** if a Wacom/Apple Pencil/Surface Pen is detected, use `QTabletEvent` for pressure data. Fall back to velocity-based width on mouse.
- Buttons below canvas: **Clear**, **Save**, **Cancel**.
- On Save: trim the QImage to the bounding box of drawn pixels (with a small padding margin, ~20px) so saved signatures aren't surrounded by huge transparent space.

**Acceptance:**
- Drawn signature exports as PNG with transparent background.
- Pasting onto a colored background shows no white box, no grey halo, no jagged edges.
- Drawing a long signature does not lag (test with strokes containing 1000+ points).

### 4.2 Storage

**What it does:** persists signatures encrypted on disk, loads them on app start.

**Requirements:**
- Storage location:
  - Windows: `%APPDATA%\SignClip\signatures.dat`
  - macOS: `~/Library/Application Support/SignClip/signatures.dat`
  - Linux: `~/.config/signclip/signatures.dat`
- File format: a single encrypted blob containing a JSON structure:
  ```json
  {
    "version": 1,
    "default_id": "uuid-string",
    "signatures": [
      {
        "id": "uuid-string",
        "name": "Full signature",
        "created_at": "2026-05-14T12:00:00Z",
        "png_b64": "base64-encoded-png-bytes"
      }
    ]
  }
  ```
- Encryption: **Fernet** (from `cryptography` library). Generate the key on first run and store it in:
  - Windows: Windows Credential Manager via `keyring` library
  - macOS: Keychain via `keyring`
  - Linux: Secret Service (GNOME Keyring / KWallet) via `keyring`
- If `keyring` is unavailable on the platform, fall back to a key file in the same folder with restricted permissions (chmod 600 on Unix). Warn the user once at startup.
- Max signatures: 10 (UI prevents adding more; this keeps the file small and the UX simple).
- All disk I/O happens off the main thread (use `QThreadPool` or `asyncio.to_thread`).

**Acceptance:**
- Killing the app and reopening restores all signatures.
- The `.dat` file, when opened in a text editor, shows only encrypted bytes (no readable PNG header, no JSON keys).
- Deleting the keyring entry makes the file unreadable (test by manually deleting and confirming the app handles it gracefully — show "Could not decrypt signatures, reset and start fresh?" dialog).

### 4.3 System Tray

**What it does:** the app lives in the system tray. Closing the editor window does not quit the app.

**Requirements:**
- Custom tray icon (provide a simple 64×64 PNG, monochrome-friendly so it works in both light and dark menu bars).
- Right-click menu:
  - **Copy default signature** (greyed out if no signatures exist)
  - Submenu **Copy signature →** lists all signatures by name
  - --- separator ---
  - **New signature...** (opens editor window)
  - **Manage signatures...** (opens manager window)
  - **Settings** (hotkey configuration)
  - --- separator ---
  - **About**
  - **Quit**
- Left-click on tray icon: copy default signature to clipboard (same as the hotkey).
- On first run, if no signatures exist, automatically open the editor window with a friendly message: "Draw your signature below to get started."

**Acceptance:**
- Closing the editor window with X does NOT quit the app; tray icon remains.
- Quit menu item is the only way to fully exit.
- On macOS, the app does not show a dock icon (set `Info.plist` key `LSUIElement = true` in PyInstaller spec, or use `QApplication.setQuitOnLastWindowClosed(False)` combined with the bundle config).

### 4.4 Global Hotkey

**What it does:** a system-wide hotkey copies the default signature to the clipboard from anywhere.

**Requirements:**
- Default hotkey: **Ctrl+Shift+S** on Windows/Linux, **Cmd+Shift+S** on macOS.
- User-configurable via the Settings window. Use `pynput.keyboard.GlobalHotKeys`.
- Hotkey must work even when the app window is closed (only the tray icon is active).
- If the chosen hotkey conflicts with another app, fail gracefully and show a tray notification: "Hotkey already in use. Choose another in Settings."
- **macOS only:** the app needs Accessibility permission to register global hotkeys. On first run, detect missing permission and show a dialog with a button that opens System Settings → Privacy → Accessibility.

**Acceptance:**
- Pressing the hotkey while focused in Microsoft Word puts the signature on the clipboard; Ctrl+V pastes it as an image.
- Same flow works in Google Docs (browser), Gmail compose, Outlook, Photoshop, Preview, and Adobe Acrobat.
- Changing the hotkey in Settings takes effect immediately without restarting the app.

### 4.5 Clipboard Copy

**What it does:** writes the signature PNG to the clipboard with its alpha channel intact.

**Requirements:**
- Use `QClipboard.setImage(qimage)` — Qt automatically registers the image in all platform-appropriate formats (PNG on macOS/Linux, DIB + PNG on Windows).
- On Windows, also explicitly register the `PNG` clipboard format to ensure Word and browsers receive the alpha channel (the legacy CF_DIB format strips transparency on some Windows targets).
- Show a brief tray notification on copy: "Signature copied. Paste anywhere." (auto-dismiss after 2 seconds, user can disable in Settings).

**Acceptance:**
- Pasting into Word: signature appears with transparent background, can be moved freely.
- Pasting into a PDF in Adobe Acrobat (Comment → Add Image, or via Edit PDF): transparency preserved.
- Pasting into a graphics app (Photoshop, Affinity, GIMP): alpha channel intact.
- Pasting into a plain text field: nothing pastes (correct — it's an image, not text).

### 4.6 Settings Window

Simple window with:
- Hotkey capture field ("Press a key combination...")
- Checkbox: "Show notification on copy"
- Checkbox: "Start at login" (uses platform-specific autostart: registry on Windows, LaunchAgent on macOS, .desktop file on Linux)
- Button: "Reset all signatures" (with confirmation dialog)
- Footer: "SignClip vX.Y.Z — local, free, open source"

### 4.7 Manager Window

Shows a list of saved signatures with thumbnails:
- Each row: thumbnail (rendered against a checkered background so the user can see transparency), name (editable inline), "Set as default" radio button, "Delete" button.
- Button at top: "+ New signature" (opens editor).
- Selecting a signature highlights the default-radio.

---

## 5. UX Flow (Happy Path)

1. User installs and launches SignClip.
2. Editor window opens automatically with the prompt to draw their first signature.
3. User draws, clicks **Save**, enters a name ("My signature"), clicks OK.
4. Editor window closes. Tray icon appears with a notification: "SignClip is running. Press Ctrl+Shift+S anywhere to paste your signature."
5. User opens Word, writes a letter, places cursor at the bottom, presses **Ctrl+Shift+S**, then **Ctrl+V**.
6. Signature appears in the document with transparent background.
7. User quits Word. SignClip is still in the tray, ready for next time.

---

## 6. Build & Distribution

### 6.1 Development setup

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
python -m signclip
```

`requirements.txt`:
```
PySide6>=6.6
pynput>=1.7
cryptography>=42
keyring>=24
```

`requirements-dev.txt`:
```
pyinstaller>=6.0
pytest>=8.0
pytest-qt>=4.0
```

### 6.2 Building binaries

`build/build.py` should produce:
- Windows: single `SignClip.exe` (PyInstaller `--onefile --windowed --icon=assets/icon.ico`)
- macOS: `SignClip.app` bundle with `LSUIElement = true` (tray-only, no dock icon)
- Linux: single binary + `.desktop` file for autostart

**Code signing is out of scope for v1** but document the unsigned-app warnings users will see on each platform in the README, with instructions for bypassing.

### 6.3 README must include

- What it is, one sentence
- Screenshot/GIF of the workflow (editor → hotkey → paste)
- Install instructions per OS
- The unsigned-binary warning workaround per OS
- Privacy statement: "SignClip makes zero network requests. Your signature is stored encrypted on your machine and never leaves it. The source code is here — verify for yourself."
- License (MIT recommended for maximum reuse)
- Build-from-source instructions

---

## 7. Acceptance Test Checklist

Manual end-to-end checks before calling v1 done:

- [ ] Fresh install on Windows 11, draw signature, paste into Word — transparent, no halo.
- [ ] Fresh install on Windows 11, paste into Google Docs in Chrome — transparent.
- [ ] Fresh install on macOS 14, grant Accessibility permission, hotkey works.
- [ ] Fresh install on macOS 14, paste into Pages — transparent.
- [ ] Fresh install on Ubuntu 24.04, paste into LibreOffice Writer — transparent.
- [ ] Kill app via Task Manager / Activity Monitor, relaunch — signatures persist.
- [ ] Open `signatures.dat` in a hex editor — no readable PNG magic bytes, no JSON keys visible.
- [ ] Delete the keyring entry, relaunch — app shows graceful "cannot decrypt" dialog, offers reset.
- [ ] Network monitor (Wireshark or Little Snitch) shows zero outbound connections during a 10-minute session of normal use.
- [ ] Two signatures saved, switch default, hotkey copies the new default.
- [ ] Change hotkey to something else, old hotkey no longer fires, new one does.
- [ ] Closing editor window does not quit app; quit menu does.
- [ ] On a 4K display with 200% scaling, canvas is not pixelated and signature exports at full resolution.

---

## 8. Out of Scope for v1

Explicitly NOT building these. Resist scope creep.

- Cross-device sync (phone → desktop). Violates "local only."
- Cloud backup. Same reason.
- PDF signing built in. Users can paste into their own PDF tool.
- Signature templates / fonts / typed signatures. Drawing only.
- Multi-user / team features.
- Auto-update. Users download a new version manually if they want one.
- Telemetry of any kind, even anonymous.
- Themes / dark mode customization (let the OS handle it via Qt's native style).

---

## 9. Build Order Recommendation

For Claude Code, build in this order so each step is testable in isolation:

1. **`paths.py` + `storage.py`** — get encrypted load/save working with hardcoded dummy data. Write unit tests.
2. **`canvas.py`** — standalone window that draws on transparent canvas and saves a PNG to disk. Visually verify transparency by opening the PNG in an image viewer with a colored background.
3. **`clipboard.py`** — copy a known PNG to clipboard, manually paste into Word/Docs to verify transparency.
4. **`editor_window.py`** — wires canvas + storage together (Save button persists via storage).
5. **`tray.py` + `app.py`** — full app lifecycle, tray menu, "Copy default" works via menu click.
6. **`hotkey.py`** — global hotkey triggers the same copy action as the tray menu.
7. **`manager_window.py`** + **Settings window** — polish.
8. **PyInstaller build** — verify it runs on a clean VM without Python installed.
9. **Acceptance checklist** — work through it on each target OS.

---

## 10. Notes for Implementation

- Use `from __future__ import annotations` in every file for cleaner type hints.
- Type hints everywhere. Run `mypy --strict` in CI.
- Use `loguru` for local debug logging (writes to app data folder, not stdout when packaged). Cap log file at 1MB rolling.
- All user-facing strings should be defined as constants in a `strings.py` module so future localization is possible without rewrites.
- Do not catch broad `Exception` except at the top-level QApplication boundary, where unhandled exceptions should show a dialog rather than silently crash the tray app.
