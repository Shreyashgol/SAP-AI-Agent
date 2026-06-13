from __future__ import annotations

from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.v1.router import api_router
from app.core.exceptions import (
    AppError,
    app_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from app.core.logging import configure_logging, get_logger
from app.core.settings import get_settings

settings = get_settings()
log = get_logger("app")


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown hooks."""
    # ── Startup ──────────────────────────────────────────────────────────────
    log.info("app.startup", env=settings.app_env)
    try:
        from app.core.startup import validate_all
        await validate_all()
    except RuntimeError as exc:
        log.error("app.startup_failed", error=str(exc))
        raise SystemExit(1) from exc

    yield  # application runs here

    # ── Shutdown ─────────────────────────────────────────────────────────────
    log.info("app.shutdown")
    try:
        from app.db.session import engine
        await engine.dispose()
        log.info("app.db_pool_closed")
    except Exception as exc:
        log.warning("app.db_pool_close_failed", exc=str(exc))

    try:
        from app.core.redis import get_redis
        redis = get_redis()
        await redis.aclose()
        log.info("app.redis_closed")
    except Exception as exc:
        log.warning("app.redis_close_failed", exc=str(exc))


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    configure_logging(debug=settings.debug)

    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_env,
            traces_sample_rate=0.05 if settings.is_production else 0.5,
        )

    app = FastAPI(
        title="Enterprise AI Intelligence Platform",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs" if not settings.is_production else None,
        redoc_url="/api/redoc" if not settings.is_production else None,
        openapi_url="/api/openapi.json" if not settings.is_production else None,
    )

    # ── Middleware (innermost first — outermost declared last) ────────────────
    from app.middleware.security_headers import SecurityHeadersMiddleware
    from app.middleware.rate_limit import RateLimitMiddleware
    from app.middleware.request_id import RequestIDMiddleware

    # RequestIDMiddleware is outermost so every response has the header
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # ── Exception handlers ────────────────────────────────────────────────────
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(api_router, prefix="/api/v1")

    # ── Prometheus metrics ────────────────────────────────────────────────────
    if settings.metrics_enabled:
        Instrumentator(
            should_group_status_codes=True,
            should_ignore_untemplated=True,
            should_group_untemplated=True,
            excluded_handlers=["/api/v1/health/live", "/api/v1/health/ready"],
        ).instrument(app).expose(
            app,
            endpoint="/metrics",
            include_in_schema=False,
            # In production the /metrics path should be blocked at the ingress
            # and only accessible from inside the cluster (Prometheus scraper).
        )

    return app


app = create_app()
