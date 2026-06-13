"""
AES-256-GCM symmetric encryption for credential storage (NFR-SEC02, DC-012).
Key loaded from ENCRYPTION_KEY env var (base64-encoded 32 bytes).
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.settings import get_settings

settings = get_settings()


def _get_key() -> bytes:
    raw = base64.b64decode(settings.encryption_key)
    if len(raw) != 32:
        raise ValueError("ENCRYPTION_KEY must be exactly 32 bytes after base64 decode.")
    return raw


def encrypt(plaintext: str) -> str:
    """Returns base64(nonce + ciphertext)."""
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt(blob: str) -> str:
    """Inverse of encrypt()."""
    key = _get_key()
    aesgcm = AESGCM(key)
    data = base64.b64decode(blob)
    nonce, ct = data[:12], data[12:]
    return aesgcm.decrypt(nonce, ct, None).decode()
