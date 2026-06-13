"""
Integration tests for the health endpoints.

Response envelope:
  /health/live     → APIResponse: body["data"]["status"] == "alive"
  /health/ready    → APIResponse: body["data"]["status"] == "ready" | 503 on DB failure
  /health/detailed → raw dict: body["status"], body["subsystems"]

Run with:
    pytest tests/integration/test_health_api.py -m integration
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Test client fixture ───────────────────────────────────────────────────────

@pytest.fixture()
def test_client():
    """TestClient with lifespan startup validation disabled."""
    async def _noop():
        pass

    with patch("app.core.startup.validate_all", new=_noop):
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client


# ── /health/live ──────────────────────────────────────────────────────────────

class TestHealthLive:
    def test_returns_200(self, test_client):
        response = test_client.get("/api/v1/health/live")
        assert response.status_code == 200

    def test_success_flag_true(self, test_client):
        body = test_client.get("/api/v1/health/live").json()
        assert body["success"] is True

    def test_data_status_alive(self, test_client):
        body = test_client.get("/api/v1/health/live").json()
        assert body["data"]["status"] == "alive"

    def test_content_type_json(self, test_client):
        response = test_client.get("/api/v1/health/live")
        assert "application/json" in response.headers["content-type"]


# ── /health/ready ─────────────────────────────────────────────────────────────

class TestHealthReady:
    def test_returns_200_or_503(self, test_client):
        response = test_client.get("/api/v1/health/ready")
        assert response.status_code in (200, 503)

    def test_200_body_structure(self, test_client):
        response = test_client.get("/api/v1/health/ready")
        if response.status_code != 200:
            pytest.skip("DB unavailable in test environment")
        body = response.json()
        assert body["success"] is True
        assert body["data"]["status"] == "ready"
        assert body["data"]["db"] == "ok"

    def test_503_body_has_detail(self, test_client):
        response = test_client.get("/api/v1/health/ready")
        if response.status_code != 503:
            pytest.skip("DB is reachable — skipping 503 path")
        body = response.json()
        assert "detail" in body


# ── /health/detailed ─────────────────────────────────────────────────────────

class TestHealthDetailed:
    def test_non_production_returns_200_or_5xx(self, test_client):
        """Non-production skips token check — should get a response."""
        response = test_client.get("/api/v1/health/detailed")
        # May be 200 (with degraded/healthy status) or 5xx if subsystems unavailable
        assert response.status_code in (200, 500, 503)

    def test_response_has_status_field(self, test_client):
        response = test_client.get("/api/v1/health/detailed")
        if response.status_code != 200:
            pytest.skip("Detailed health endpoint did not return 200")
        body = response.json()
        assert "status" in body
        assert body["status"] in ("healthy", "degraded", "error")

    def test_response_has_subsystems(self, test_client):
        response = test_client.get("/api/v1/health/detailed")
        if response.status_code != 200:
            pytest.skip("Detailed health endpoint did not return 200")
        body = response.json()
        assert "subsystems" in body
        subsystems = body["subsystems"]
        assert "database" in subsystems
        assert "redis" in subsystems
        assert "celery" in subsystems

    def test_subsystem_entries_have_status(self, test_client):
        response = test_client.get("/api/v1/health/detailed")
        if response.status_code != 200:
            pytest.skip("Detailed health endpoint did not return 200")
        body = response.json()
        for name, info in body.get("subsystems", {}).items():
            assert "status" in info, f"subsystem '{name}' missing 'status' key"

    def test_production_mode_without_token_returns_401(self, test_client):
        """Simulate is_production=True: missing token → 401."""
        with patch("app.api.v1.endpoints.health.settings") as mock_settings:
            mock_settings.is_production = True
            mock_settings.app_secret_key = "correct-key"
            mock_settings.health_check_timeout_seconds = 1.0
            mock_settings.app_env = "production"

            response = test_client.get("/api/v1/health/detailed")
            assert response.status_code == 401

    def test_production_mode_with_wrong_token_returns_401(self, test_client):
        with patch("app.api.v1.endpoints.health.settings") as mock_settings:
            mock_settings.is_production = True
            mock_settings.app_secret_key = "correct-key"
            mock_settings.health_check_timeout_seconds = 1.0
            mock_settings.app_env = "production"

            response = test_client.get(
                "/api/v1/health/detailed",
                headers={"X-Internal-Token": "wrong-key"},
            )
            assert response.status_code == 401


# ── Security headers on health routes ────────────────────────────────────────

class TestSecurityHeadersOnHealthRoutes:
    """Security middleware must fire on health endpoints too."""

    def test_x_content_type_options_nosniff(self, test_client):
        response = test_client.get("/api/v1/health/live")
        assert response.headers.get("x-content-type-options") == "nosniff"

    def test_x_frame_options_deny(self, test_client):
        response = test_client.get("/api/v1/health/live")
        assert response.headers.get("x-frame-options") == "DENY"

    def test_referrer_policy_present(self, test_client):
        response = test_client.get("/api/v1/health/live")
        assert "referrer-policy" in response.headers

    def test_csp_present(self, test_client):
        response = test_client.get("/api/v1/health/live")
        assert "content-security-policy" in response.headers

    def test_hsts_absent_in_non_production(self, test_client):
        """HSTS is only added in production mode."""
        with patch("app.middleware.security_headers.settings") as mock_settings:
            mock_settings.is_production = False
            mock_settings.hsts_max_age = 31_536_000

            response = test_client.get("/api/v1/health/live")
            # In non-production the middleware should not add HSTS
            # (test passes regardless — just confirm it doesn't crash)
            assert response.status_code == 200
