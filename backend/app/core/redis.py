import asyncio

import redis.asyncio as aioredis

from app.core.settings import get_settings

settings = get_settings()

# One client per event loop: an asyncio Redis client is bound to the loop it was
# created on, so a process-wide singleton breaks when multiple loops exist
# (tests, Celery). In production there is a single loop, so this is a singleton.
_clients: dict[int, aioredis.Redis] = {}


def _get_redis_client() -> aioredis.Redis:
    try:
        loop_id = id(asyncio.get_running_loop())
    except RuntimeError:
        # Called from a non-async thread (e.g. FastAPI sync dependency resolution).
        # Connections are created lazily on first await, so a process-wide
        # default client is safe here — the server has a single loop.
        loop_id = 0
    client = _clients.get(loop_id)
    if client is None:
        client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        _clients[loop_id] = client
    return client


def get_redis() -> aioredis.Redis:
    """FastAPI dependency — returns the shared Redis client."""
    return _get_redis_client()


# ── Namespaced key helpers ────────────────────────────────────────────────────

def blocklist_key(jti: str) -> str:
    return f"auth:blocklist:{jti}"


def lockout_key(tenant_id: str, email: str) -> str:
    return f"auth:lockout:{tenant_id}:{email}"


def rate_limit_user_key(user_id: str) -> str:
    return f"rl:user:{user_id}"


def rate_limit_tenant_key(tenant_id: str) -> str:
    return f"rl:tenant:{tenant_id}"


def session_key(session_id: str) -> str:
    return f"session:{session_id}"
