"""
Unit tests: JWT creation/verification, password hashing, lockout.
"""

import pytest
from jose import JWTError

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)


@pytest.mark.unit
def test_password_hash_and_verify() -> None:
    hashed = hash_password("correct-horse-battery-staple")
    assert verify_password("correct-horse-battery-staple", hashed)
    assert not verify_password("wrong-password", hashed)


@pytest.mark.unit
def test_hash_is_bcrypt() -> None:
    hashed = hash_password("test")
    assert hashed.startswith("$2b$")


@pytest.mark.unit
def test_access_token_roundtrip() -> None:
    user_id = "user-123"
    tenant_id = "tenant-abc"
    roles = ["business_user"]
    token, jti = create_access_token(user_id, tenant_id, roles)
    payload = decode_access_token(token)
    assert payload["sub"] == user_id
    assert payload["tenant_id"] == tenant_id
    assert payload["roles"] == roles
    assert payload["jti"] == jti
    assert payload["type"] == "access"


@pytest.mark.unit
def test_refresh_token_roundtrip() -> None:
    token, jti = create_refresh_token("user-123", "tenant-abc")
    payload = decode_refresh_token(token)
    assert payload["type"] == "refresh"
    assert payload["jti"] == jti


@pytest.mark.unit
def test_access_token_rejected_as_refresh() -> None:
    token, _ = create_access_token("user-123", "tenant-abc", [])
    with pytest.raises(JWTError):
        decode_refresh_token(token)


@pytest.mark.unit
def test_refresh_token_rejected_as_access() -> None:
    token, _ = create_refresh_token("user-123", "tenant-abc")
    with pytest.raises(JWTError):
        decode_access_token(token)


@pytest.mark.unit
def test_tampered_token_rejected() -> None:
    token, _ = create_access_token("user-123", "tenant-abc", [])
    tampered = token[:-10] + "XXXXXXXXXX"
    with pytest.raises(JWTError):
        decode_access_token(tampered)
