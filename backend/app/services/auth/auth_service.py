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

# A *valid* bcrypt hash used only to keep the "user not found" path timing-safe
# (prevents email enumeration). The previous placeholder was malformed, so
# passlib raised ValueError → HTTP 500 on every unknown-email login instead of a
# clean 401. Computed once at import.
_DUMMY_HASH = hash_password("timing-safe-dummy-password")


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

        log.info("auth.login.success", user_id=str(user.id), tenant_id=str(tenant_id))
        return await self._issue_session(user)

    # ── Register (self-serve org signup) ───────────────────────────────────────
    async def register_organization(
        self, organization_name: str, full_name: str, email: str, password: str
    ) -> tuple[LoginResponse, str]:
        """Create a new organization (tenant) + its first platform_admin user,
        then sign that user in. Email must be globally unique so sign-in can
        resolve the tenant from the email alone."""
        from app.core.exceptions import ConflictError
        from app.services.auth.rbac_service import RBACService

        existing = await self.db.execute(select(User).where(User.email == email))
        if existing.scalars().first():
            raise ConflictError("An account with this email already exists.")

        slug = await self._unique_slug(organization_name)
        tenant, admin_user = await RBACService(self.db).bootstrap_tenant(
            name=organization_name,
            slug=slug,
            admin_email=email,
            admin_password=password,
            admin_name=full_name,
        )
        if admin_user is None:  # pragma: no cover — bootstrap always makes the admin here
            raise ConflictError("Could not provision the admin account.")

        log.info("auth.register.success", user_id=str(admin_user.id), tenant_id=str(tenant.id))
        return await self._issue_session(admin_user)

    # ── Password reset ─────────────────────────────────────────────────────────
    async def request_password_reset(self, email: str) -> str | None:
        """Issue a single-use reset token (stored in Redis, 30-min TTL) for the
        user with this email. Returns the token, or None if no single active user
        matches (the endpoint responds identically either way to avoid leaking
        which emails exist)."""
        import secrets

        result = await self.db.execute(
            select(User).where(User.email == email, User.is_active.is_(True))
        )
        users = list(result.scalars().all())
        if len(users) != 1:
            return None

        token = secrets.token_urlsafe(32)
        await self.redis.setex(f"auth:reset:{token}", 1800, str(users[0].id))
        log.info("auth.reset.requested", user_id=str(users[0].id))
        return token

    async def reset_password(self, token: str, new_password: str) -> None:
        """Consume a reset token and set the new password (clearing any lockout)."""
        stored = await self.redis.get(f"auth:reset:{token}")
        if not stored:
            raise UnauthorizedError("This reset link is invalid or has expired.")
        user_id = stored.decode() if isinstance(stored, bytes) else stored

        user = await self._get_user_by_id(uuid.UUID(user_id))
        user.hashed_password = hash_password(new_password)
        user.failed_login_attempts = 0
        user.locked_until = None
        await self.db.commit()

        await self.redis.delete(f"auth:reset:{token}")
        log.info("auth.reset.success", user_id=str(user.id))

    async def resolve_tenant_for_email(self, email: str) -> uuid.UUID | None:
        """Find the tenant for a sign-in by email. Returns the tenant id when
        exactly one active user has this email, else None (ambiguous/none)."""
        result = await self.db.execute(
            select(User.tenant_id).where(User.email == email, User.is_active.is_(True))
        )
        tenant_ids = list(result.scalars().all())
        return tenant_ids[0] if len(tenant_ids) == 1 else None

    async def _issue_session(self, user: User) -> tuple[LoginResponse, str]:
        """Mint the access token + refresh token (recording the refresh jti) and
        build the LoginResponse. Shared by login and register."""
        roles, domains = await self._get_roles_and_domains(user)
        access_token, _ = create_access_token(str(user.id), str(user.tenant_id), roles)
        refresh_token, refresh_jti = create_refresh_token(str(user.id), str(user.tenant_id))

        # Store refresh jti → user mapping (TTL = refresh lifetime)
        ttl = settings.jwt_refresh_token_expire_days * 86400
        await self.redis.setex(f"auth:refresh:{refresh_jti}", ttl, str(user.id))

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

    async def _unique_slug(self, name: str) -> str:
        """Derive a URL-safe, unique tenant slug from the organization name."""
        import re
        import secrets

        from app.models.tenant import Tenant

        base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "org"
        slug = base
        for _ in range(5):
            exists = await self.db.execute(select(Tenant.id).where(Tenant.slug == slug))
            if not exists.scalar_one_or_none():
                return slug
            slug = f"{base}-{secrets.token_hex(3)}"
        return f"{base}-{secrets.token_hex(4)}"

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
            # Timing-safe: still run verify against a valid hash to prevent enumeration
            verify_password("dummy", _DUMMY_HASH)
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
