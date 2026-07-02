"""
Security response headers (NFR-SEC09).

Headers applied to every response:
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: geolocation=(), camera=(), microphone=()
  Content-Security-Policy: (permissive for API — tightened for production)
  Strict-Transport-Security: (production only, configurable max-age)

The API is JSON-only so CSP is deliberately minimal. The frontend SPA
enforces its own CSP via a separate nginx config.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.settings import get_settings

settings = get_settings()

_STATIC_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}

_HSTS_HEADER = f"max-age={settings.hsts_max_age}; includeSubDomains; preload"

# Swagger UI / ReDoc load CSS + JS from the jsDelivr CDN, run an inline
# bootstrap script, and pull a favicon from fastapi.tiangolo.com. The strict
# API CSP blocks all of that, so the interactive docs pages get a scoped,
# relaxed policy instead.
_DOCS_PATHS = ("/api/docs", "/api/redoc")
_DOCS_CSP = (
    "default-src 'none'; "
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "img-src 'self' https://fastapi.tiangolo.com data:; "
    "font-src 'self' https://cdn.jsdelivr.net; "
    "connect-src 'self'; "
    "frame-ancestors 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for header, value in _STATIC_HEADERS.items():
            response.headers[header] = value
        if request.url.path in _DOCS_PATHS:
            response.headers["Content-Security-Policy"] = _DOCS_CSP
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = _HSTS_HEADER
        return response
