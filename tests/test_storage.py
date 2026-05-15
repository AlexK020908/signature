from __future__ import annotations

from pathlib import Path

import pytest

from signclip import storage
from signclip.storage import (
    DecryptError,
    Signature,
    SignatureStore,
    MAX_SIGNATURES,
    StorageError,
)


def _png(label: bytes = b"x") -> bytes:
    # Smallest-possible PNG header + data label for round-trip testing.
    # (We don't decode in these tests; we treat png_bytes as opaque.)
    return b"\x89PNG\r\n\x1a\n" + label * 32


def _save_load(tmp_path: Path, store: SignatureStore) -> SignatureStore:
    sig_path = tmp_path / "signatures.dat"
    key_path = tmp_path / "signclip.key"
    storage.save(store, signatures_path=sig_path, keyfile_path=key_path)
    return storage.load(signatures_path=sig_path, keyfile_path=key_path)


def test_store_add_default_and_iterate():
    store = SignatureStore()
    s1 = Signature.create("First", _png(b"a"))
    s2 = Signature.create("Second", _png(b"b"))
    store.add(s1)
    store.add(s2)
    assert store.default_id == s1.id
    assert store.default().name == "First"
    store.set_default(s2.id)
    assert store.default().name == "Second"


def test_store_delete_reassigns_default():
    store = SignatureStore()
    s1 = Signature.create("First", _png(b"a"))
    s2 = Signature.create("Second", _png(b"b"))
    store.add(s1)
    store.add(s2)
    store.set_default(s2.id)
    store.delete(s2.id)
    assert store.default_id == s1.id


def test_max_signatures_enforced():
    store = SignatureStore()
    for i in range(MAX_SIGNATURES):
        store.add(Signature.create(f"s{i}", _png()))
    with pytest.raises(StorageError):
        store.add(Signature.create("overflow", _png()))


def test_round_trip_persistence(tmp_path):
    store = SignatureStore()
    s = Signature.create("Hello", _png(b"hello-bytes"))
    store.add(s)
    loaded = _save_load(tmp_path, store)
    assert len(loaded) == 1
    assert loaded.default_id == s.id
    assert loaded.signatures[0].png_bytes == s.png_bytes
    assert loaded.signatures[0].name == "Hello"


def test_file_is_encrypted(tmp_path):
    store = SignatureStore()
    store.add(Signature.create("Encrypted", _png(b"plaintext-marker-xyz")))
    sig_path = tmp_path / "signatures.dat"
    key_path = tmp_path / "signclip.key"
    storage.save(store, signatures_path=sig_path, keyfile_path=key_path)

    raw = sig_path.read_bytes()
    # No PNG magic bytes and no plaintext JSON keys should be visible.
    assert b"\x89PNG" not in raw
    assert b"png_b64" not in raw
    assert b"signatures" not in raw
    assert b"plaintext-marker-xyz" not in raw


def test_decrypt_fails_with_wrong_key(tmp_path):
    from cryptography.fernet import Fernet

    store = SignatureStore()
    store.add(Signature.create("Hello", _png()))
    sig_path = tmp_path / "signatures.dat"
    key_a = Fernet.generate_key()
    key_b = Fernet.generate_key()
    storage.save(store, signatures_path=sig_path, key=key_a)

    with pytest.raises(DecryptError):
        storage.load(signatures_path=sig_path, key=key_b)


def test_rename_signature():
    store = SignatureStore()
    s = Signature.create("Old", _png())
    store.add(s)
    store.rename(s.id, "New")
    assert store.find(s.id).name == "New"
