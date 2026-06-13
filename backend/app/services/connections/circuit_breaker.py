"""
Per-connection circuit breaker (Spec 1.5, Part 7.2).
States: CLOSED → OPEN (after 5 failures in 60s) → HALF_OPEN (after 120s cool-down).
State persisted in Redis so all workers share the same view.
"""

import time
from enum import Enum

import redis.asyncio as aioredis

FAILURE_THRESHOLD = 5
FAILURE_WINDOW = 60    # seconds — count failures within this window
OPEN_DURATION = 120    # seconds — stay open before trying again


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, redis: aioredis.Redis, connection_id: str) -> None:
        self._redis = redis
        self._connection_id = connection_id
        self._state_key = f"cb:state:{connection_id}"
        self._fail_key = f"cb:fails:{connection_id}"
        self._opened_at_key = f"cb:opened_at:{connection_id}"

    async def state(self) -> CircuitState:
        raw = await self._redis.get(self._state_key)
        if raw is None:
            return CircuitState.CLOSED
        state = CircuitState(raw)
        if state == CircuitState.OPEN:
            opened_at = float(await self._redis.get(self._opened_at_key) or 0)
            if time.time() - opened_at >= OPEN_DURATION:
                await self._redis.set(self._state_key, CircuitState.HALF_OPEN)
                return CircuitState.HALF_OPEN
        return state

    async def is_open(self) -> bool:
        return await self.state() == CircuitState.OPEN

    async def record_success(self) -> None:
        await self._redis.delete(self._state_key)
        await self._redis.delete(self._fail_key)
        await self._redis.delete(self._opened_at_key)

    async def record_failure(self) -> None:
        pipe = self._redis.pipeline()
        pipe.incr(self._fail_key)
        pipe.expire(self._fail_key, FAILURE_WINDOW)
        results = await pipe.execute()
        fail_count = results[0]

        if fail_count >= FAILURE_THRESHOLD:
            await self._redis.set(self._state_key, CircuitState.OPEN)
            await self._redis.set(self._opened_at_key, str(time.time()))
            await self._redis.expire(self._state_key, OPEN_DURATION * 2)
