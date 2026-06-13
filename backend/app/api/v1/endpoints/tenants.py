"""
Tenant bootstrap and user management.
POST /tenants — create tenant (superadmin only; dev: open)
POST /tenants/{tenant_id}/users — create user within tenant
GET  /tenants/{tenant_id}/users — list users (platform_admin)
POST /tenants/{tenant_id}/users/{user_id}/roles — assign role
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, RequirePlatformAdmin
from app.db.session import get_db
from app.models.user import Role, RolePermission, UserRole
from app.schemas.base import APIResponse, PaginatedResponse
from app.schemas.user import (
    AssignRoleRequest,
    TenantCreate,
    TenantResponse,
    UserCreate,
    UserResponse,
)
from app.services.auth.rbac_service import RBACService

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("", response_model=APIResponse[TenantResponse], status_code=201)
async def create_tenant(
    body: TenantCreate,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[TenantResponse]:
    svc = RBACService(db)
    tenant, _ = await svc.bootstrap_tenant(
        name=body.name,
        slug=body.slug,
        timezone=body.timezone,
    )
    return APIResponse(
        data=TenantResponse(
            id=str(tenant.id),
            name=tenant.name,
            slug=tenant.slug,
            timezone=tenant.timezone,
            is_active=tenant.is_active,
        ),
        message="Tenant created. Bootstrap your first admin user at POST /tenants/{id}/users.",
    )


@router.post("/{tenant_id}/users", response_model=APIResponse[UserResponse], status_code=201)
async def create_user(
    tenant_id: uuid.UUID,
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[UserResponse]:
    svc = RBACService(db)
    user = await svc.create_user(
        tenant_id=tenant_id,
        email=body.email,
        full_name=body.full_name,
        password=body.password,
        role_names=body.role_names,
    )
    roles_result = await db.execute(
        select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user.id)
    )
    roles = [r[0] for r in roles_result.fetchall()]
    domains_result = await db.execute(
        select(RolePermission.domain)
        .join(Role, Role.id == RolePermission.role_id)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id)
    )
    domains = list({r[0] for r in domains_result.fetchall()})
    return APIResponse(
        data=UserResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            tenant_id=str(user.tenant_id),
            is_active=user.is_active,
            roles=roles,
            domains=domains,
        ),
        message="User created.",
    )


@router.post(
    "/{tenant_id}/users/{user_id}/roles",
    response_model=APIResponse[None],
    dependencies=[RequirePlatformAdmin],
)
async def assign_role(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    body: AssignRoleRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[None]:
    svc = RBACService(db)
    await svc.assign_role(tenant_id, user_id, body.role_name, current_user.id)
    return APIResponse(message=f"Role '{body.role_name}' assigned.")
