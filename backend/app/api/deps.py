"""
API dependency injection — re-exports from core plus tenant-scoped helpers.

Endpoints import from here: `from app.api.deps import RequirePlatformAdmin, get_current_tenant`
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (  # noqa: F401
    CurrentUser,
    RequirePlatformAdmin,
    RequirePowerUserOrAbove,
    get_current_user,
    get_user_domains,
    get_user_role_names,
    require_domain,
    require_roles,
)
from app.db.session import get_db
from app.models.user import User


async def get_current_tenant(
    user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Returns a dict with tenant_id (UUID) and user_id (UUID) for the current request.
    Extracted from the JWT payload stored on the User object.
    """
    payload = getattr(user, "_token_payload", {})
    tenant_id_str = payload.get("tenant_id")
    tenant_id = uuid.UUID(tenant_id_str) if tenant_id_str else user.tenant_id

    return {
        "id": tenant_id,
        "user_id": user.id,
        "user": user,
    }
