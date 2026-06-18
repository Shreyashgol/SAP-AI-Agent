"""
FastAPI dependency injection — current user resolution + RBAC enforcement.

Login has been removed: every request runs as the default user (the first
active user in the database). On a fresh database, a default tenant and
platform_admin user are bootstrapped automatically on the first request.
"""

import secrets
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError
from app.core.redis import get_redis
from app.db.session import get_db
from app.models.tenant import Tenant
from app.models.user import Role, RolePermission, User, UserRole

# re-export so endpoint files can do: from app.core.deps import get_redis
__all__ = ["get_redis", "get_current_user", "CurrentUser", "get_user_domains",
           "get_user_role_names", "require_roles", "require_domain",
           "RequirePlatformAdmin", "RequirePowerUserOrAbove"]

DEFAULT_TENANT_NAME = "Default"
DEFAULT_TENANT_SLUG = "default"
DEFAULT_USER_EMAIL = "admin@example.com"
DEFAULT_USER_NAME = "Default Admin"



# ── Current user ──────────────────────────────────────────────────────────────

async def get_current_user(
    db: AsyncSession = Depends(get_db),
) -> User:
    result = await db.execute(
        select(User)
        .where(User.is_active.is_(True))
        .order_by(User.created_at)
        .limit(1)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = await _bootstrap_default_user(db)
    return user


async def _bootstrap_default_user(db: AsyncSession) -> User:
    from app.services.auth.rbac_service import RBACService

    svc = RBACService(db)
    tenant_result = await db.execute(
        select(Tenant).order_by(Tenant.created_at).limit(1)
    )
    tenant = tenant_result.scalar_one_or_none()
    # Password is unused (login is removed) but the column requires a hash.
    if tenant is None:
        _, user = await svc.bootstrap_tenant(
            name=DEFAULT_TENANT_NAME,
            slug=DEFAULT_TENANT_SLUG,
            admin_email=DEFAULT_USER_EMAIL,
            admin_password=secrets.token_urlsafe(24),
            admin_name=DEFAULT_USER_NAME,
        )
        if user is None:
            raise RuntimeError("Failed to bootstrap admin user for default tenant.")
        return user
    return await svc.create_user(
        tenant_id=tenant.id,
        email=DEFAULT_USER_EMAIL,
        full_name=DEFAULT_USER_NAME,
        password=secrets.token_urlsafe(24),
        role_names=["platform_admin"],
    )


CurrentUser = Annotated[User, Depends(get_current_user)]


# ── Role / Domain helpers ─────────────────────────────────────────────────────

async def get_user_domains(user: User, db: AsyncSession) -> set[str]:
    result = await db.execute(
        select(RolePermission.domain)
        .join(Role, Role.id == RolePermission.role_id)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id, RolePermission.can_read.is_(True))
    )
    return {row[0] for row in result.fetchall()}


async def get_user_role_names(user: User, db: AsyncSession) -> set[str]:
    result = await db.execute(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id)
    )
    return {row[0] for row in result.fetchall()}


# ── Permission factories ──────────────────────────────────────────────────────

def require_roles(*role_names: str):
    """Dependency factory: user must hold at least one of the given roles."""
    async def _check(
        user: CurrentUser,
        db: AsyncSession = Depends(get_db),
    ) -> User:
        roles = await get_user_role_names(user, db)
        if not roles.intersection(role_names):
            raise ForbiddenError()
        return user
    return _check


def require_domain(domain: str):
    """Dependency factory: user must have read access to the given data domain."""
    async def _check(
        user: CurrentUser,
        db: AsyncSession = Depends(get_db),
    ) -> User:
        domains = await get_user_domains(user, db)
        if domain not in domains:
            raise ForbiddenError(f"You do not have access to the {domain} domain.")
        return user
    return _check


# Shorthand composites
RequirePlatformAdmin = Depends(require_roles("platform_admin"))
RequirePowerUserOrAbove = Depends(require_roles("platform_admin", "power_user"))
