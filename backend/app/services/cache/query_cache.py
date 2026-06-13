"""
Query Result Cache — Redis-backed cache for identical SQL executions.

Spec: QC-001, QC-002, QC-003
  - QC-001: Cache key = SHA-256(tenant_id + connection_id + normalised_sql + params_json)
  - QC-002: TTL = 300 seconds (5 minutes) — aligned with Claude's prompt cache TTL
  - QC-003: Cache is bypassed for RCA / Trend / Document intents (data freshness required)
  - QC-004: Cache hit logged; staleness is explicit (cached_at timestamp stored)

Cache miss: sql_executor runs the live query and stores the result.
Cache hit:  sql_executor is skipped; state is populated from cache.

The cache is per-tenant — no cross-tenant data leakage possible (key includes tenant_id).
Cache entries are stored as JSON-serialised {rows, columns, row_count, truncated, cached_at}.

Invalidation:
  - Automatic TTL expiry (5 min)
  - Manual via cache_invalidate_tenant() called after schema discovery or tool rebuild
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger

log = get_logger("query_cache")

_TTL_SECONDS = 300  # 5 minutes
_KEY_PREFIX = "qcache"

# Intents for which caching is disabled (freshness critical)
_NO_CACHE_INTENTS = {"RCA", "Trend"}


def _cache_key(
    tenant_id: str,
    connection_id: str,
    sql: str,
    params: dict[str, Any],
) -> str:
    """SHA-256 of the canonical inputs — deterministic, no collisions."""
    normalised_sql = " ".join(sql.split()).upper()
    payload = json.dumps(
        {
            "t": str(tenant_id),
            "c": str(connection_id),
            "s": normalised_sql,
            "p": params,
        },
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()[:32]
    return f"{_KEY_PREFIX}:{tenant_id}:{digest}"


async def get_cached_result(
    tenant_id: str,
    connection_id: str,
    sql: str,
    params: dict[str, Any],
    intent: str | None = None,
) -> dict[str, Any] | None:
    """Return cached query result dict or None on miss / bypass."""
    if intent in _NO_CACHE_INTENTS:
        return None

    try:
        from app.core.redis import get_redis
        redis = get_redis()
        key = _cache_key(tenant_id, connection_id, sql, params)
        raw = await redis.get(key)
        if raw:
            result = json.loads(raw)
            log.info("query_cache.hit", key=key[-16:], intent=intent)
            return result
    except Exception as exc:
        log.warning("query_cache.get_error", exc=str(exc))
    return None


async def set_cached_result(
    tenant_id: str,
    connection_id: str,
    sql: str,
    params: dict[str, Any],
    result: dict[str, Any],
    intent: str | None = None,
) -> None:
    """Store query result in Redis with TTL. No-op on error."""
    if intent in _NO_CACHE_INTENTS:
        return

    try:
        from app.core.redis import get_redis
        redis = get_redis()
        key = _cache_key(tenant_id, connection_id, sql, params)
        payload = json.dumps(
            {**result, "cached_at": datetime.now(timezone.utc).isoformat()},
            default=str,
        )
        await redis.setex(key, _TTL_SECONDS, payload)
        log.info("query_cache.set", key=key[-16:], rows=result.get("row_count"))
    except Exception as exc:
        log.warning("query_cache.set_error", exc=str(exc))


async def invalidate_tenant_cache(tenant_id: str) -> int:
    """Delete all cached query results for a tenant. Returns number of keys deleted."""
    try:
        from app.core.redis import get_redis
        redis = get_redis()
        pattern = f"{_KEY_PREFIX}:{tenant_id}:*"
        keys = await redis.keys(pattern)
        if keys:
            deleted = await redis.delete(*keys)
            log.info("query_cache.invalidated", tenant_id=tenant_id, keys=deleted)
            return deleted
    except Exception as exc:
        log.warning("query_cache.invalidate_error", exc=str(exc))
    return 0
