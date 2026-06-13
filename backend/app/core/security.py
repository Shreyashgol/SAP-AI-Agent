"""
JWT creation/verification + password hashing.
Access token: 8h, signed HS256, carries: sub (user_id), tenant_id, jti (for blocklist).
Refresh token: 30d, httpOnly cookie, separate jti.
"""

import uuid
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.settings import get_settings

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


# ── Password ──────────────────────────────────────────────────────────────────
def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── Token creation ────────────────────────────────────────────────────────────
def _make_token(
    subject: str,
    tenant_id: str,
    token_type: str,
    expires_delta: timedelta,
    extra: dict | None = None,
) -> tuple[str, str]:
    """Returns (encoded_jwt, jti)."""
    jti = str(uuid.uuid4())
    now = datetime.now(UTC)
    payload: dict = {
        "sub": subject,
        "tenant_id": tenant_id,
        "type": token_type,
        "jti": jti,
        "iat": now,
        "exp": now + expires_delta,
    }
    if extra:
        payload.update(extra)
    encoded = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded, jti


def create_access_token(user_id: str, tenant_id: str, roles: list[str]) -> tuple[str, str]:
    delta = timedelta(hours=settings.jwt_access_token_expire_hours)
    return _make_token(user_id, tenant_id, ACCESS_TOKEN_TYPE, delta, {"roles": roles})


def create_refresh_token(user_id: str, tenant_id: str) -> tuple[str, str]:
    delta = timedelta(days=settings.jwt_refresh_token_expire_days)
    return _make_token(user_id, tenant_id, REFRESH_TOKEN_TYPE, delta)


# ── Token verification ────────────────────────────────────────────────────────
def decode_token(token: str) -> dict:
    """Raises JWTError on any invalid token."""
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def decode_access_token(token: str) -> dict:
    payload = decode_token(token)
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise JWTError("Not an access token")
    return payload


def decode_refresh_token(token: str) -> dict:
    payload = decode_token(token)
    if payload.get("type") != REFRESH_TOKEN_TYPE:
        raise JWTError("Not a refresh token")
    return payload
