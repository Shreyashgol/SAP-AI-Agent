"""
Admin REST API — user management within a tenant.

Spec: AU-001, AU-002, AU-003
  - GET  /admin/users             — list all users for tenant
  - POST /admin/users/invite      — create user + send invite (stub delivery)
  - PATCH /admin/users/{id}       — toggle active / update full_name
  - GET  /admin/users/{id}/roles  — list user's roles
  - POST /admin/users/{id}/roles  — assign a role
  - DELETE /admin/users/{id}/roles/{role_id} — revoke a role

Access control: only platform_admin or power_user roles may call admin endpoints.
Enforced via _require_admin() dependency.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.security import hash_password
from app.models.user import Role, User, UserRole
from app.core.logging import get_logger

log = get_logger("admin")
router = APIRouter(prefix="/admin", tags=["admin"])


# ── Schemas (inline — admin-only, no public API contract) ────────────────────

class UserInvite(BaseModel):
    email: EmailStr
    full_name: str
    role_id: uuid.UUID | None = None


class UserPatch(BaseModel):
    full_name: str | None = None
    is_active: bool | None = None


class UserSummary(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_sso: bool
    tenant_id: uuid.UUID
    created_at: str

    model_config = {"from_attributes": True}


class RoleSummary(BaseModel):
    id: uuid.UUID
    name: str
    is_system: bool
    description: str | None

    model_config = {"from_attributes": True}


class UserRoleSummary(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    role_id: uuid.UUID
    assigned_by: uuid.UUID | None

    model_config = {"from_attributes": True}


class RoleAssign(BaseModel):
    role_id: uuid.UUID


# ── Auth guard ────────────────────────────────────────────────────────────────

async def _require_admin(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify the caller holds platform_admin or power_user role."""
    result = await db.execute(
        select(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            UserRole.user_id == current_user.id,
            Role.name.in_(["platform_admin", "power_user"]),
        )
    )
    if result.first() is None:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# ── User endpoints ────────────────────────────────────────────────────────────

@router.get("/users", response_model=list[UserSummary])
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    admin=Depends(_require_admin),
):
    result = await db.execute(
        select(User)
        .where(User.tenant_id == admin.tenant_id)
        .order_by(User.full_name)
    )
    return result.scalars().all()


@router.post("/users/invite", response_model=UserSummary, status_code=status.HTTP_201_CREATED)
async def invite_user(
    body: UserInvite,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin=Depends(_require_admin),
):
    # Check duplicate email within tenant
    existing = await db.execute(
        select(User).where(
            User.tenant_id == admin.tenant_id,
            User.email == body.email,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    # Create user with a temporary password (user must reset on first login)
    import secrets
    temp_password = secrets.token_urlsafe(16)
    user = User(
        tenant_id=admin.tenant_id,
        email=body.email,
        full_name=body.full_name,
        hashed_password=hash_password(temp_password),
        is_active=True,
        is_sso=False,
    )
    db.add(user)
    await db.flush()  # get user.id before role assignment

    # Optionally assign role
    if body.role_id:
        role_check = await db.execute(
            select(Role).where(
                Role.id == body.role_id,
                Role.tenant_id == admin.tenant_id,
            )
        )
        if role_check.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Role not found")
        user_role = UserRole(
            user_id=user.id,
            role_id=body.role_id,
            assigned_by=admin.id,
        )
        db.add(user_role)

    await db.commit()
    await db.refresh(user)

    # Delivery stub — real email invite is Phase 6
    log.info("admin.user_invited", email=body.email, invited_by=str(admin.id))

    return user


@router.patch("/users/{user_id}", response_model=UserSummary)
async def patch_user(
    user_id: uuid.UUID,
    body: UserPatch,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin=Depends(_require_admin),
):
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.tenant_id == admin.tenant_id,
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(user, field, val)
    await db.commit()
    await db.refresh(user)
    return user


# ── Role assignment ───────────────────────────────────────────────────────────

@router.get("/users/{user_id}/roles", response_model=list[UserRoleSummary])
async def list_user_roles(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin=Depends(_require_admin),
):
    # Verify user belongs to tenant
    res = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == admin.tenant_id)
    )
    if res.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="User not found")

    result = await db.execute(
        select(UserRole).where(UserRole.user_id == user_id)
    )
    return result.scalars().all()


@router.post("/users/{user_id}/roles", response_model=UserRoleSummary, status_code=status.HTTP_201_CREATED)
async def assign_role(
    user_id: uuid.UUID,
    body: RoleAssign,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin=Depends(_require_admin),
):
    res = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == admin.tenant_id)
    )
    if res.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Idempotent — skip if already assigned
    existing = await db.execute(
        select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.role_id == body.role_id,
        )
    )
    ur = existing.scalar_one_or_none()
    if ur:
        return ur

    ur = UserRole(user_id=user_id, role_id=body.role_id, assigned_by=admin.id)
    db.add(ur)
    await db.commit()
    await db.refresh(ur)
    return ur


@router.delete("/users/{user_id}/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_role(
    user_id: uuid.UUID,
    role_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin=Depends(_require_admin),
):
    result = await db.execute(
        select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.role_id == role_id,
        )
    )
    ur = result.scalar_one_or_none()
    if ur is None:
        raise HTTPException(status_code=404, detail="Role assignment not found")
    await db.delete(ur)
    await db.commit()


# ── Roles listing (for dropdowns) ─────────────────────────────────────────────

@router.get("/roles", response_model=list[RoleSummary])
async def list_roles(
    db: Annotated[AsyncSession, Depends(get_db)],
    admin=Depends(_require_admin),
):
    result = await db.execute(
        select(Role)
        .where(Role.tenant_id == admin.tenant_id)
        .order_by(Role.name)
    )
    return result.scalars().all()
