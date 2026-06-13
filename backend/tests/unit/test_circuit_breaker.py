"""
Circuit breaker unit tests — state transitions.
Uses fakeredis for in-memory Redis.
"""

import pytest
import pytest_asyncio

try:
    import fakeredis.aioredis as fakeredis  # type: ignore[import-untyped]
    HAS_FAKEREDIS = True
except ImportError:
    HAS_FAKEREDIS = False

from app.services.connections.circuit_breaker import (
    FAILURE_THRESHOLD,
    CircuitBreaker,
    CircuitState,
)

pytestmark = pytest.mark.skipif(not HAS_FAKEREDIS, reason="fakeredis not installed")


@pytest_asyncio.fixture
async def redis():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest_asyncio.fixture
async def breaker(redis):
    return CircuitBreaker(redis, "test-conn-id")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_initial_state_is_closed(breaker) -> None:
    assert await breaker.state() == CircuitState.CLOSED
    assert not await breaker.is_open()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_opens_after_threshold_failures(breaker) -> None:
    for _ in range(FAILURE_THRESHOLD):
        await breaker.record_failure()
    assert await breaker.state() == CircuitState.OPEN
    assert await breaker.is_open()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_success_resets_to_closed(breaker) -> None:
    for _ in range(FAILURE_THRESHOLD):
        await breaker.record_failure()
    await breaker.record_success()
    assert await breaker.state() == CircuitState.CLOSED


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fewer_than_threshold_stays_closed(breaker) -> None:
    for _ in range(FAILURE_THRESHOLD - 1):
        await breaker.record_failure()
    assert await breaker.state() == CircuitState.CLOSED
