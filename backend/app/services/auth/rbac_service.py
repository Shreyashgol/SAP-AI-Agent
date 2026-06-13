"""
RBAC bootstrap and management.

4 system roles:
  platform_admin  — all domains, full access
  power_user      — all domains, read + export
  business_user   — assigned domains, read only
  viewer          — assigned domains, read only (no export)

5 data domains: finance | sales | purchasing | inventory | operations
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.user import Role, RolePermission, User, UserRole

SYSTEM_ROLES: list[dict] = [
    {
        "name": "platform_admin",
        "description": "Full platform access — all domains, all features.",
        "domains": ["finance", "sales", "purchasing", "inventory", "operations"],
        "can_export": True,
    },
    {
        "name": "power_user",
        "description": "All domains, can export.",
        "domains": ["finance", "sales", "purchasing", "inventory", "operations"],
        "can_export": True,
    },
    {
        "name": "business_user",
        "description": "Assigned domains, read only.",
        "domains": [],  # assigned explicitly per user
        "can_export": False,
    },
    {
        "name": "viewer",
        "description": "Read-only access to assigned domains.",
        "domains": [],
        "can_export": False,
    },
]

ALL_DOMAINS = ["finance", "sales", "purchasing", "inventory", "operations"]


class RBACService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Tenant bootstrap ──────────────────────────────────────────────────────
    async def bootstrap_tenant(
        self,
        name: str,
        slug: str,
        timezone: str = "UTC",
        admin_email: str | None = None,
        admin_password: str | None = None,
        admin_name: str = "Admin",
    ) -> tuple[Tenant, User | None]:
        """
        Creates tenant + all 4 system roles + role_permissions.
        Optionally creates the first platform_admin user.
        """
        # Check slug uniqueness
        existing = await self.db.execute(
            select(Tenant).where(Tenant.slug == slug)
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"Tenant slug '{slug}' is already taken.")

        tenant = Tenant(name=name, slug=slug, timezone=timezone)
        self.db.add(tenant)
        await self.db.flush()

        # Create system roles + permissions
        role_map: dict[str, Role] = {}
        for role_def in SYSTEM_ROLES:
            role = Role(
                tenant_id=tenant.id,
                name=role_def["name"],
                description=role_def["description"],
                is_system=True,
            )
            self.db.add(role)
            await self.db.flush()
            role_map[role_def["name"]] = role

            # Admin and power_user get all domains with permissions
            domains = role_def["domains"] if role_def["domains"] else []
            for domain in domains:
                self.db.add(
                    RolePermission(
                        role_id=role.id,
                        domain=domain,
                        can_read=True,
                        can_export=role_def["can_export"],
                    )
                )

        await self.db.flush()

        # Optionally create the first admin user
        admin_user = None
        if admin_email and admin_password:
            admin_user = await self._create_user(
                tenant_id=tenant.id,
                email=admin_email,
                full_name=admin_name,
                password=admin_password,
                roles=[role_map["platform_admin"]],
            )

        await self.db.commit()
        return tenant, admin_user

    # ── User management ───────────────────────────────────────────────────────
    async def create_user(
        self,
        tenant_id: uuid.UUID,
        email: str,
        full_name: str,
        password: str,
        role_names: list[str],
        domains: list[str] | None = None,
    ) -> User:
        # Check uniqueness
        existing = await self.db.execute(
            select(User).where(User.tenant_id == tenant_id, User.email == email)
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"User with email '{email}' already exists.")

        roles = await self._resolve_roles(tenant_id, role_names)
        user = await self._create_user(tenant_id, email, full_name, password, roles)

        # Assign domain permissions to non-system roles if specified
        if domains:
            for role in roles:
                if not role.is_system:
                    for domain in domains:
                        self.db.add(
                            RolePermission(
                                role_id=role.id,
                                domain=domain,
                                can_read=True,
                                can_export=False,
                            )
                        )

        await self.db.commit()
        return user

    async def assign_role(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        role_name: str,
        assigned_by: uuid.UUID,
    ) -> None:
        roles = await self._resolve_roles(tenant_id, [role_name])
        role = roles[0]
        existing = await self.db.execute(
            select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role.id)
        )
        if existing.scalar_one_or_none():
            return  # Already assigned — idempotent
        self.db.add(UserRole(user_id=user_id, role_id=role.id, assigned_by=assigned_by))
        await self.db.commit()

    # ── Internal helpers ──────────────────────────────────────────────────────
    async def _create_user(
        self,
        tenant_id: uuid.UUID,
        email: str,
        full_name: str,
        password: str,
        roles: list[Role],
    ) -> User:
        user = User(
            tenant_id=tenant_id,
            email=email,
            full_name=full_name,
            hashed_password=hash_password(password),
        )
        self.db.add(user)
        await self.db.flush()
        for role in roles:
            self.db.add(UserRole(user_id=user.id, role_id=role.id))
        await self.db.flush()
        return user

    async def _resolve_roles(self, tenant_id: uuid.UUID, role_names: list[str]) -> list[Role]:
        result = await self.db.execute(
            select(Role).where(Role.tenant_id == tenant_id, Role.name.in_(role_names))
        )
        roles = result.scalars().all()
        found = {r.name for r in roles}
        missing = set(role_names) - found
        if missing:
            raise NotFoundError(f"Roles not found: {', '.join(missing)}")
        return list(roles)
