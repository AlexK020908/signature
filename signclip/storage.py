from __future__ import annotations

import base64
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from cryptography.fernet import Fernet, InvalidToken

from signclip import paths

KEYRING_SERVICE = "SignClip"
KEYRING_USER = "encryption-key"
STORAGE_VERSION = 1
MAX_SIGNATURES = 10


class StorageError(Exception):
    """Base class for storage errors."""


class DecryptError(StorageError):
    """Raised when stored signatures cannot be decrypted."""


@dataclass
class Signature:
    id: str
    name: str
    created_at: str
    png_bytes: bytes

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "png_b64": base64.b64encode(self.png_bytes).decode("ascii"),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, str]) -> Signature:
        return cls(
            id=raw["id"],
            name=raw["name"],
            created_at=raw["created_at"],
            png_bytes=base64.b64decode(raw["png_b64"]),
        )

    @classmethod
    def create(cls, name: str, png_bytes: bytes) -> Signature:
        return cls(
            id=str(uuid.uuid4()),
            name=name,
            created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            png_bytes=png_bytes,
        )


@dataclass
class SignatureStore:
    signatures: list[Signature] = field(default_factory=list)
    default_id: str | None = None

    def default(self) -> Signature | None:
        if not self.signatures:
            return None
        for sig in self.signatures:
            if sig.id == self.default_id:
                return sig
        return self.signatures[0]

    def find(self, sig_id: str) -> Signature | None:
        for sig in self.signatures:
            if sig.id == sig_id:
                return sig
        return None

    def add(self, sig: Signature) -> None:
        if len(self.signatures) >= MAX_SIGNATURES:
            raise StorageError(
                f"Cannot save more than {MAX_SIGNATURES} signatures."
            )
        self.signatures.append(sig)
        if self.default_id is None:
            self.default_id = sig.id

    def delete(self, sig_id: str) -> None:
        self.signatures = [s for s in self.signatures if s.id != sig_id]
        if self.default_id == sig_id:
            self.default_id = self.signatures[0].id if self.signatures else None

    def set_default(self, sig_id: str) -> None:
        if not self.find(sig_id):
            raise StorageError("Signature not found.")
        self.default_id = sig_id

    def rename(self, sig_id: str, new_name: str) -> None:
        sig = self.find(sig_id)
        if sig is None:
            raise StorageError("Signature not found.")
        sig.name = new_name.strip() or sig.name

    def iter(self) -> Iterable[Signature]:
        return iter(self.signatures)

    def __len__(self) -> int:
        return len(self.signatures)


# ---------- key management ----------------------------------------------------


def _load_or_create_key(
    *,
    signatures_path: Path | None = None,
    keyfile_path: Path | None = None,
    on_fallback: Callable[[], None] | None = None,
) -> bytes:
    """Resolve the Fernet key.

    Tries the OS keyring first. If unavailable, falls back to a file with
    restricted permissions in the app data folder.
    """
    keyfile = keyfile_path or paths.keyfile_fallback()
    try:
        import keyring

        existing = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
        if existing:
            return existing.encode("ascii")
        new_key = Fernet.generate_key()
        keyring.set_password(KEYRING_SERVICE, KEYRING_USER, new_key.decode("ascii"))
        return new_key
    except Exception:
        if on_fallback is not None:
            try:
                on_fallback()
            except Exception:
                pass
        if keyfile.exists():
            return keyfile.read_bytes().strip()
        new_key = Fernet.generate_key()
        keyfile.write_bytes(new_key)
        if sys.platform != "win32":
            try:
                os.chmod(keyfile, 0o600)
            except OSError:
                pass
        return new_key


def reset_key() -> None:
    """Remove keyring entry and fallback keyfile (used when the user resets)."""
    try:
        import keyring

        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USER)
        except Exception:
            pass
    except Exception:
        pass
    kf = paths.keyfile_fallback()
    if kf.exists():
        try:
            kf.unlink()
        except OSError:
            pass


# ---------- load / save -------------------------------------------------------


def load(
    *,
    signatures_path: Path | None = None,
    keyfile_path: Path | None = None,
    on_fallback: Callable[[], None] | None = None,
    key: bytes | None = None,
) -> SignatureStore:
    path = signatures_path or paths.signatures_file()
    if not path.exists():
        return SignatureStore()
    if key is None:
        key = _load_or_create_key(
            signatures_path=path, keyfile_path=keyfile_path, on_fallback=on_fallback
        )
    blob = path.read_bytes()
    try:
        plaintext = Fernet(key).decrypt(blob)
    except InvalidToken as exc:
        raise DecryptError("Could not decrypt signatures file.") from exc
    data = json.loads(plaintext.decode("utf-8"))
    if data.get("version") != STORAGE_VERSION:
        raise StorageError(f"Unknown storage version: {data.get('version')!r}")
    sigs = [Signature.from_dict(d) for d in data.get("signatures", [])]
    return SignatureStore(signatures=sigs, default_id=data.get("default_id"))


def save(
    store: SignatureStore,
    *,
    signatures_path: Path | None = None,
    keyfile_path: Path | None = None,
    on_fallback: Callable[[], None] | None = None,
    key: bytes | None = None,
) -> None:
    path = signatures_path or paths.signatures_file()
    if key is None:
        key = _load_or_create_key(
            signatures_path=path, keyfile_path=keyfile_path, on_fallback=on_fallback
        )
    payload = {
        "version": STORAGE_VERSION,
        "default_id": store.default_id,
        "signatures": [s.to_dict() for s in store.signatures],
    }
    plaintext = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    blob = Fernet(key).encrypt(plaintext)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(blob)
    os.replace(tmp, path)


def reset_all() -> None:
    """Delete signatures file and key. Used by Settings → Reset."""
    sf = paths.signatures_file()
    if sf.exists():
        try:
            sf.unlink()
        except OSError:
            pass
    reset_key()
