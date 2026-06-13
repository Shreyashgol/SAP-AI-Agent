"""
AES-256 encryption roundtrip tests.
"""

import base64
import os

import pytest


@pytest.mark.unit
def test_encrypt_decrypt_roundtrip(monkeypatch) -> None:
    # Provide a valid 32-byte key
    key_bytes = os.urandom(32)
    monkeypatch.setenv("ENCRYPTION_KEY", base64.b64encode(key_bytes).decode())

    # Re-import to pick up the monkeypatched env
    from importlib import reload
    import app.core.encryption as enc_module
    reload(enc_module)

    plaintext = "postgresql://user:supersecret@host:5432/db"
    blob = enc_module.encrypt(plaintext)
    assert blob != plaintext
    assert enc_module.decrypt(blob) == plaintext


@pytest.mark.unit
def test_different_encryptions_produce_different_blobs(monkeypatch) -> None:
    key_bytes = os.urandom(32)
    monkeypatch.setenv("ENCRYPTION_KEY", base64.b64encode(key_bytes).decode())

    from importlib import reload
    import app.core.encryption as enc_module
    reload(enc_module)

    b1 = enc_module.encrypt("same plaintext")
    b2 = enc_module.encrypt("same plaintext")
    # GCM uses random nonce each time — blobs must differ
    assert b1 != b2
    assert enc_module.decrypt(b1) == enc_module.decrypt(b2) == "same plaintext"
