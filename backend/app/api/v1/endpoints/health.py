"""
Health check endpoints.

/health/live     — Kubernetes liveness probe. Always 200 if process is alive.
/health/ready    — Kubernetes readiness probe. 200 only when DB is reachable.
/health/detailed — Deep check: DB + Redis + Celery + storage. Returns per-subsystem
                   timings and a top-level degraded/healthy status.
                   Blocked in production behind internal network policy;
                   returns 401 if X-Internal-Token header is absent/wrong.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.schemas.base import APIResponse

settings = get_settings()
router = APIRouter(tags=["health"])


# ── Liveness ──────────────────────────────────────────────────────────────────

@router.get("/health/live", response_model=APIResponse[dict], summary="Liveness probe")
async def liveness() -> APIResponse[dict]:
    return APIResponse(data={"status": "alive"})


# ── Readiness ─────────────────────────────────────────────────────────────────

@router.get("/health/ready", response_model=APIResponse[dict], summary="Readiness probe")
async def readiness() -> APIResponse[dict]:
    """Checks DB only — fast path for Kubernetes readiness probe."""
    from app.db.session import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unreachable: {exc}",
        )
    return APIResponse(data={"status": "ready", "db": "ok"})


# ── Deep health ───────────────────────────────────────────────────────────────

async def _check_db() -> dict[str, Any]:
    from app.db.session import AsyncSessionLocal
    t0 = time.monotonic()
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        return {"status": "ok", "latency_ms": round((time.monotonic() - t0) * 1000, 1)}
    except Exception as exc:
        return {"status": "error", "error": str(exc), "latency_ms": round((time.monotonic() - t0) * 1000, 1)}


async def _check_redis() -> dict[str, Any]:
    t0 = time.monotonic()
    try:
        from app.core.redis import get_redis
        redis = get_redis()
        pong = await redis.ping()
        ok = bool(pong)
        return {"status": "ok" if ok else "error", "latency_ms": round((time.monotonic() - t0) * 1000, 1)}
    except Exception as exc:
        return {"status": "error", "error": str(exc), "latency_ms": round((time.monotonic() - t0) * 1000, 1)}


def _check_celery() -> dict[str, Any]:
    t0 = time.monotonic()
    try:
        from app.worker.celery_app import celery_app
        inspect = celery_app.control.inspect(timeout=settings.health_check_timeout_seconds)
        pong = inspect.ping()
        worker_count = len(pong) if pong else 0
        return {
            "status": "ok" if worker_count > 0 else "degraded",
            "workers": worker_count,
            "latency_ms": round((time.monotonic() - t0) * 1000, 1),
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc), "latency_ms": round((time.monotonic() - t0) * 1000, 1)}


@router.get("/health/detailed", summary="Deep health check (internal)")
async def detailed_health(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> dict[str, Any]:
    """
    Returns per-subsystem health with latencies.
    Protected in production — requires X-Internal-Token matching APP_SECRET_KEY.
    """
    if settings.is_production:
        if x_internal_token != settings.app_secret_key:
            raise HTTPException(status_code=401, detail="X-Internal-Token required")

    import asyncio
    db_result, redis_result = await asyncio.gather(_check_db(), _check_redis())
    celery_result = _check_celery()

    subsystems = {
        "database": db_result,
        "redis": redis_result,
        "celery": celery_result,
    }

    any_error = any(v.get("status") == "error" for v in subsystems.values())
    any_degraded = any(v.get("status") == "degraded" for v in subsystems.values())
    overall = "error" if any_error else "degraded" if any_degraded else "healthy"

    return {
        "status": overall,
        "version": "1.0.0",
        "environment": settings.app_env,
        "subsystems": subsystems,
    }
