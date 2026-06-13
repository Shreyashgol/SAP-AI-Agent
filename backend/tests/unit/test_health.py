"""Health endpoint smoke tests — Sprint 0 exit criterion."""

import pytest
from httpx import AsyncClient


@pytest.mark.unit
@pytest.mark.asyncio
async def test_liveness(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/live")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "alive"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_liveness_has_request_id_header(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/live")
    assert "X-Request-ID" in response.headers


@pytest.mark.unit
@pytest.mark.asyncio
async def test_request_id_echoed_back(client: AsyncClient) -> None:
    rid = "test-request-id-123"
    response = await client.get("/api/v1/health/live", headers={"X-Request-ID": rid})
    assert response.headers["X-Request-ID"] == rid


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unknown_route_returns_404(client: AsyncClient) -> None:
    response = await client.get("/api/v1/nonexistent")
    assert response.status_code == 404


@pytest.mark.unit
@pytest.mark.asyncio
async def test_error_response_shape(client: AsyncClient) -> None:
    response = await client.get("/api/v1/nonexistent")
    # FastAPI default 404 — just check it's JSON
    assert response.headers["content-type"].startswith("application/json")
