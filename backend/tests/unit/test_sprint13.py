"""
Sprint 13 unit tests — production hardening.

Coverage:
  - Dockerfile: multi-stage structure (builder + runtime targets exist)
  - docker-compose.prod.yml: resource limits, named volumes, no bind-mount for source
  - nginx.prod.conf: /metrics blocked, HSTS present, rate limit zones defined
  - redis.prod.conf: maxmemory set, eviction policy, FLUSHALL disabled
  - locustfile: task classes importable without a live server
  - .env.production.example: no raw secrets, documents key variables present
  - .gitignore: .env.production and ssl/ directory excluded

All tests use plain file-read assertions — no external services required.
"""

from __future__ import annotations

import os
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent.parent


# ── Dockerfile ────────────────────────────────────────────────────────────────

class TestApiDockerfile:
    _path = REPO_ROOT / "backend" / "Dockerfile"

    def test_file_exists(self):
        assert self._path.exists()

    def test_has_builder_stage(self):
        content = self._path.read_text()
        assert "AS builder" in content

    def test_has_runtime_stage(self):
        content = self._path.read_text()
        assert "AS runtime" in content

    def test_runs_as_non_root(self):
        content = self._path.read_text()
        assert "USER appuser" in content or "useradd" in content

    def test_uses_gunicorn(self):
        content = self._path.read_text()
        assert "gunicorn" in content

    def test_healthcheck_defined(self):
        content = self._path.read_text()
        assert "HEALTHCHECK" in content

    def test_no_dev_tools_installed(self):
        content = self._path.read_text()
        # pip should not install dev requirements in the runtime image
        assert "requirements-dev.txt" not in content


class TestFrontendDockerfile:
    _path = REPO_ROOT / "frontend" / "Dockerfile"

    def test_file_exists(self):
        assert self._path.exists()

    def test_has_node_builder_stage(self):
        content = self._path.read_text()
        assert "node:" in content.lower()

    def test_has_nginx_runtime_stage(self):
        content = self._path.read_text()
        assert "nginx" in content.lower()

    def test_copies_dist_to_html(self):
        content = self._path.read_text()
        assert "/app/dist" in content
        assert "nginx/html" in content


# ── docker-compose.prod.yml ───────────────────────────────────────────────────

class TestProdDockerCompose:
    _path = REPO_ROOT / "docker-compose.prod.yml"

    def _content(self) -> str:
        return self._path.read_text()

    def test_file_exists(self):
        assert self._path.exists()

    def test_app_env_production(self):
        assert "APP_ENV=production" in self._content()

    def test_debug_false(self):
        assert "DEBUG=false" in self._content()

    def test_resource_limits_defined(self):
        content = self._content()
        assert "resources:" in content
        assert "limits:" in content

    def test_no_source_bind_mount(self):
        content = self._content()
        # Dev compose mounts ./backend:/app — prod must not
        assert "./backend:/app" not in content
        assert "./frontend:/app" not in content

    def test_named_volumes_for_data(self):
        content = self._content()
        assert "platform_documents:" in content
        assert "platform_reports:" in content

    def test_redis_password_set(self):
        content = self._content()
        assert "REDIS_PASSWORD" in content

    def test_restart_always(self):
        content = self._content()
        assert "restart: always" in content


# ── nginx.prod.conf ───────────────────────────────────────────────────────────

class TestNginxProdConf:
    _path = REPO_ROOT / "infra" / "nginx" / "nginx.prod.conf"

    def _content(self) -> str:
        return self._path.read_text()

    def test_file_exists(self):
        assert self._path.exists()

    def test_metrics_blocked(self):
        content = self._content()
        assert "/metrics" in content
        assert "deny all" in content

    def test_hsts_header_present(self):
        content = self._content()
        assert "Strict-Transport-Security" in content
        assert "max-age=31536000" in content

    def test_tls_1_2_and_1_3_only(self):
        content = self._content()
        assert "TLSv1.2" in content
        assert "TLSv1.3" in content
        assert "TLSv1 " not in content or "TLSv1.1" not in content

    def test_rate_limit_zones_defined(self):
        content = self._content()
        assert "limit_req_zone" in content

    def test_auth_rate_limit_stricter(self):
        content = self._content()
        assert "auth_limit" in content

    def test_gzip_enabled(self):
        content = self._content()
        assert "gzip on" in content

    def test_http_redirects_to_https(self):
        content = self._content()
        assert "return 301 https://" in content

    def test_x_frame_options_deny(self):
        content = self._content()
        assert "X-Frame-Options" in content
        assert "DENY" in content


# ── redis.prod.conf ───────────────────────────────────────────────────────────

class TestRedisProdConf:
    _path = REPO_ROOT / "infra" / "redis" / "redis.prod.conf"

    def _content(self) -> str:
        return self._path.read_text()

    def test_file_exists(self):
        assert self._path.exists()

    def test_maxmemory_set(self):
        assert "maxmemory" in self._content()

    def test_eviction_policy_lru(self):
        content = self._content()
        assert "allkeys-lru" in content or "maxmemory-policy" in content

    def test_flushall_disabled(self):
        content = self._content()
        assert 'rename-command FLUSHALL  ""' in content or 'FLUSHALL ""' in content

    def test_aof_enabled(self):
        content = self._content()
        assert "appendonly yes" in content


# ── .env.production.example ───────────────────────────────────────────────────

class TestEnvProductionExample:
    _path = REPO_ROOT / ".env.production.example"

    def _content(self) -> str:
        return self._path.read_text()

    def test_file_exists(self):
        assert self._path.exists()

    def test_app_env_production(self):
        assert "APP_ENV=production" in self._content()

    def test_no_real_secrets(self):
        content = self._content()
        # Placeholder markers — no actual sk-ant- keys
        assert "sk-ant-api03-..." in content or "sk-ant-..." in content
        assert "sk-ant-api03-a" not in content  # no real key prefix

    def test_encryption_key_documented(self):
        assert "ENCRYPTION_KEY" in self._content()

    def test_jwt_keys_documented(self):
        content = self._content()
        assert "JWT_SECRET_KEY" in content
        assert "APP_SECRET_KEY" in content

    def test_nfr_c05_note_present(self):
        assert "NFR-C05" in self._content()


# ── .gitignore ────────────────────────────────────────────────────────────────

class TestGitignore:
    _path = REPO_ROOT / ".gitignore"

    def _content(self) -> str:
        return self._path.read_text()

    def test_env_production_excluded(self):
        assert ".env.production" in self._content()

    def test_ssl_dir_excluded(self):
        content = self._content()
        assert "ssl/" in content or "infra/nginx/ssl/" in content

    def test_pem_files_excluded(self):
        assert "*.pem" in self._content()

    def test_env_example_not_excluded(self):
        content = self._content()
        assert "!.env.example" in content


# ── locustfile importability ──────────────────────────────────────────────────

class TestLocustfile:
    def test_locustfile_importable(self):
        import importlib.util, sys
        load_path = str(REPO_ROOT / "backend" / "tests" / "load" / "locustfile.py")
        spec = importlib.util.spec_from_file_location("locustfile", load_path)
        try:
            mod = importlib.util.module_from_spec(spec)
            # Suppress locust's gevent monkey-patching in unit test context
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
        except ImportError:
            pytest.skip("locust not installed — run: pip install locust")

    def test_conversation_user_class_defined(self):
        import importlib.util
        load_path = str(REPO_ROOT / "backend" / "tests" / "load" / "locustfile.py")
        spec = importlib.util.spec_from_file_location("locustfile", load_path)
        try:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            assert hasattr(mod, "ConversationUser")
            assert hasattr(mod, "DashboardUser")
            assert hasattr(mod, "HealthUser")
        except ImportError:
            pytest.skip("locust not installed")
