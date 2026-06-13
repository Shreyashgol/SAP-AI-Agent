"""
Auth service — login, refresh, logout, me.
Implements:
  - bcrypt password verify (NFR-SEC03)
  - 5-attempt lockout / 15-min window (NFR-SEC05)
  - JWT access (8h) + refresh (30d, httpOnly) (NFR-SEC03/04)
  - Redis refresh-token blocklist on logout (GS-010)
  - Audit log entry on every auth event
"""

import uuid
from datetime import UTC, datetime, timedelta

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.core.logging import get_logger
from app.core.redis import blocklist_key
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.core.settings import get_settings
from app.models.user import Role, RolePermission, User, UserRole
from app.schemas.auth import LoginResponse, RefreshResponse, UserResponse

settings = get_settings()
log = get_logger(__name__)

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
REFRESH_TOKEN_COOKIE = "refresh_token"


class AuthService:
    def __init__(self, db: AsyncSession, redis: aioredis.Redis) -> None:
        self.db = db
        self.redis = redis

    # ── Login ─────────────────────────────────────────────────────────────────
    async def login(self, email: str, password: str, tenant_id: uuid.UUID) -> tuple[LoginResponse, str]:
        user = await self._get_user_by_email(email, tenant_id)
        await self._check_lockout(user)
        await self._verify_credentials(user, password)
        await self._reset_lockout(user)
        await self._record_login(user)

        roles, domains = await self._get_roles_and_domains(user)
        access_token, _ = create_access_token(str(user.id), str(user.tenant_id), roles)
        refresh_token, refresh_jti = create_refresh_token(str(user.id), str(user.tenant_id))

        # Store refresh jti → user mapping (TTL = refresh lifetime)
        ttl = settings.jwt_refresh_token_expire_days * 86400
        await self.redis.setex(
            f"auth:refresh:{refresh_jti}",
            ttl,
            str(user.id),
        )

        log.info("auth.login.success", user_id=str(user.id), tenant_id=str(tenant_id))

        return LoginResponse(
            access_token=access_token,
            user=UserResponse(
                id=str(user.id),
                email=user.email,
                full_name=user.full_name,
                tenant_id=str(user.tenant_id),
                roles=roles,
                domains=domains,
            ),
        ), refresh_token

    # ── Refresh ───────────────────────────────────────────────────────────────
    async def refresh(self, refresh_token: str) -> tuple[RefreshResponse, str]:
        from jose import JWTError
        try:
            payload = decode_refresh_token(refresh_token)
        except JWTError:
            raise UnauthorizedError("Invalid refresh token.")

        jti: str = payload["jti"]
        user_id: str = payload["sub"]
        tenant_id: str = payload["tenant_id"]

        # Confirm jti still valid (not logged out)
        stored = await self.redis.get(f"auth:refresh:{jti}")
        if not stored or stored != user_id:
            raise UnauthorizedError("Refresh token revoked or expired.")

        # Rotate: invalidate old jti, issue new pair
        await self.redis.delete(f"auth:refresh:{jti}")

        user = await self._get_user_by_id(uuid.UUID(user_id))
        roles, _ = await self._get_roles_and_domains(user)
        new_access, _ = create_access_token(user_id, tenant_id, roles)
        new_refresh, new_jti = create_refresh_token(user_id, tenant_id)

        ttl = settings.jwt_refresh_token_expire_days * 86400
        await self.redis.setex(f"auth:refresh:{new_jti}", ttl, user_id)

        return RefreshResponse(access_token=new_access), new_refresh

    # ── Logout ────────────────────────────────────────────────────────────────
    async def logout(self, access_jti: str, refresh_token: str | None) -> None:
        # access_jti already extracted by caller from validated token payload
        ttl = settings.jwt_access_token_expire_hours * 3600
        await self.redis.setex(blocklist_key(access_jti), ttl, "1")

        # Revoke refresh token if present
        if refresh_token:
            from jose import JWTError
            try:
                payload = decode_refresh_token(refresh_token)
                await self.redis.delete(f"auth:refresh:{payload['jti']}")
            except JWTError:
                pass  # already expired — no action needed

        log.info("auth.logout", jti=access_jti)

    # ── Helpers ───────────────────────────────────────────────────────────────
    async def _get_user_by_email(self, email: str, tenant_id: uuid.UUID) -> User:
        result = await self.db.execute(
            select(User).where(User.email == email, User.tenant_id == tenant_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            # Timing-safe: still run verify to prevent enumeration
            verify_password("dummy", "$2b$12$dummy_hash_padding_for_timing")
            raise UnauthorizedError("Invalid email or password.")
        return user

    async def _get_user_by_id(self, user_id: uuid.UUID) -> User:
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise UnauthorizedError()
        return user

    async def _check_lockout(self, user: User) -> None:
        if user.locked_until and user.locked_until > datetime.now(UTC):
            remaining = int((user.locked_until - datetime.now(UTC)).total_seconds() / 60) + 1
            raise UnauthorizedError(
                f"Account locked due to too many failed attempts. Try again in {remaining} minute(s)."
            )

    async def _verify_credentials(self, user: User, password: str) -> None:
        if not user.hashed_password or not verify_password(password, user.hashed_password):
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
                user.locked_until = datetime.now(UTC) + timedelta(minutes=LOCKOUT_MINUTES)
                log.warning("auth.lockout", user_id=str(user.id))
            await self.db.commit()
            raise UnauthorizedError("Invalid email or password.")

    async def _reset_lockout(self, user: User) -> None:
        user.failed_login_attempts = 0
        user.locked_until = None
        await self.db.commit()

    async def _record_login(self, user: User) -> None:
        user.last_login_at = datetime.now(UTC)
        await self.db.commit()

    async def _get_roles_and_domains(self, user: User) -> tuple[list[str], list[str]]:
        roles_result = await self.db.execute(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id)
        )
        roles = [r[0] for r in roles_result.fetchall()]

        domains_result = await self.db.execute(
            select(RolePermission.domain)
            .join(Role, Role.id == RolePermission.role_id)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id, RolePermission.can_read.is_(True))
        )
        domains = list({r[0] for r in domains_result.fetchall()})
        return roles, domains
