"""
Sliding-window rate limiting (NFR-SEC08):
  - 60 req/min per authenticated user
  - 100 req/min per tenant
Returns 429 with Retry-After header on breach.
Uses Redis INCR + EXPIRE for atomic sliding windows.
"""

import time

from fastapi import Request, status
from fastapi.responses import JSONResponse
from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.redis import get_redis, rate_limit_tenant_key, rate_limit_user_key
from app.core.security import decode_access_token
from app.core.settings import get_settings
from app.schemas.base import ErrorDetail, ErrorResponse

settings = get_settings()

WINDOW = 60  # seconds


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip health checks and auth endpoints
        path = request.url.path
        if path.startswith("/api/v1/health") or path in ("/api/v1/auth/login", "/api/v1/auth/refresh"):
            return await call_next(request)

        redis = get_redis()
        now_window = int(time.time() // WINDOW)

        user_id: str | None = None
        tenant_id: str | None = None

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                payload = decode_access_token(auth_header.removeprefix("Bearer ").strip())
                user_id = payload.get("sub")
                tenant_id = payload.get("tenant_id")
            except JWTError:
                pass

        # Per-user limit
        if user_id:
            key = f"{rate_limit_user_key(user_id)}:{now_window}"
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, WINDOW * 2)
            if count > settings.rate_limit_per_user:
                return self._too_many(request, WINDOW - int(time.time() % WINDOW))

        # Per-tenant limit
        if tenant_id:
            key = f"{rate_limit_tenant_key(tenant_id)}:{now_window}"
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, WINDOW * 2)
            if count > settings.rate_limit_per_tenant:
                return self._too_many(request, WINDOW - int(time.time() % WINDOW))

        return await call_next(request)

    def _too_many(self, request: Request, retry_after: int) -> JSONResponse:
        rid = request.headers.get("X-Request-ID", "-")
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(retry_after)},
            content=ErrorResponse(
                error=ErrorDetail(
                    code="RATE_LIMITED",
                    message="Too many requests. Please slow down.",
                ),
                request_id=rid,
            ).model_dump(),
        )
