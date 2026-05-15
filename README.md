# SignClip

A free, local-only desktop app: draw your signature once, paste it as a transparent PNG anywhere with a global hotkey.

## Privacy

SignClip makes **zero network requests**. Your signature is stored encrypted on your machine and never leaves it. The source code is here — verify for yourself.

- No accounts, no sign-up, no email.
- No telemetry, no analytics, no update checks.
- Signature stored encrypted with a per-machine key held in the OS keyring (Windows Credential Manager / macOS Keychain / Secret Service).

## Workflow

1. Launch SignClip — the editor opens automatically on first run.
2. Draw your signature, click **Save**, give it a name.
3. SignClip lives in the system tray.
4. Anywhere in any app, press **Ctrl+Shift+S** (or **Cmd+Shift+S** on macOS), then paste with **Ctrl+V**.

## Install

### From source

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
python -m signclip
```

### Pre-built binaries

Download from the releases page. Binaries are unsigned (code-signing is out of scope for v1).

**Windows:** SmartScreen will warn "Windows protected your PC". Click **More info → Run anyway**.

**macOS:** First-launch will say the app cannot be opened because Apple cannot check it for malware. Right-click the app → **Open** → **Open** in the dialog. You will also need to grant **Accessibility** permission (System Settings → Privacy & Security → Accessibility) so the global hotkey can register.

**Linux:** `chmod +x SignClip && ./SignClip`.

## Build from source

```bash
pip install -r requirements-dev.txt
python build/build.py
```

## License

MIT.
