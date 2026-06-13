"""
Auth endpoints: login, refresh, logout, me.
Refresh token travels as httpOnly cookie — never in JSON body (GS-010).
"""

import uuid
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Cookie, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_redis
from app.core.settings import get_settings
from app.db.session import get_db
from app.schemas.auth import LoginRequest, LoginResponse, RefreshResponse, UserResponse
from app.schemas.base import APIResponse
from app.services.auth.auth_service import AuthService, REFRESH_TOKEN_COOKIE

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])

_COOKIE_OPTS = dict(
    key=REFRESH_TOKEN_COOKIE,
    httponly=True,
    secure=settings.is_production,
    samesite="lax",
    max_age=settings.jwt_refresh_token_expire_days * 86400,
    path="/api/v1/auth",
)


def _svc(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> AuthService:
    return AuthService(db, redis)


@router.post("/login", response_model=APIResponse[LoginResponse])
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    svc: AuthService = Depends(_svc),
) -> APIResponse[LoginResponse]:
    # Tenant resolved from X-Tenant-ID header (or first tenant for dev convenience)
    tenant_header = request.headers.get("X-Tenant-ID", "")
    try:
        tenant_id = uuid.UUID(tenant_header)
    except ValueError:
        from app.core.exceptions import UnauthorizedError
        raise UnauthorizedError("Missing or invalid X-Tenant-ID header.")

    login_response, refresh_token = await svc.login(body.email, body.password, tenant_id)
    response.set_cookie(value=refresh_token, **_COOKIE_OPTS)
    return APIResponse(data=login_response)


@router.post("/refresh", response_model=APIResponse[RefreshResponse])
async def refresh(
    response: Response,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_TOKEN_COOKIE)] = None,
    svc: AuthService = Depends(_svc),
) -> APIResponse[RefreshResponse]:
    if not refresh_token:
        from app.core.exceptions import UnauthorizedError
        raise UnauthorizedError("No refresh token.")
    refresh_response, new_refresh_token = await svc.refresh(refresh_token)
    response.set_cookie(value=new_refresh_token, **_COOKIE_OPTS)
    return APIResponse(data=refresh_response)


@router.post("/logout", response_model=APIResponse[None])
async def logout(
    request: Request,
    response: Response,
    current_user: CurrentUser,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_TOKEN_COOKIE)] = None,
    svc: AuthService = Depends(_svc),
) -> APIResponse[None]:
    payload = getattr(current_user, "_token_payload", {})
    access_jti: str = payload.get("jti", "")
    await svc.logout(access_jti, refresh_token)
    response.delete_cookie(REFRESH_TOKEN_COOKIE, path="/api/v1/auth")
    return APIResponse(message="Logged out successfully.")


@router.get("/me", response_model=APIResponse[UserResponse])
async def me(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[UserResponse]:
    from app.core.deps import get_user_role_names, get_user_domains
    roles = list(await get_user_role_names(current_user, db))
    domains = list(await get_user_domains(current_user, db))
    return APIResponse(
        data=UserResponse(
            id=str(current_user.id),
            email=current_user.email,
            full_name=current_user.full_name,
            tenant_id=str(current_user.tenant_id),
            roles=roles,
            domains=domains,
        )
    )
