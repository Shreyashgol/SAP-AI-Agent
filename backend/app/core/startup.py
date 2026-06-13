"""
Startup validation — fail fast with clear error messages if critical
infrastructure is unreachable or misconfigured at launch time.

Called from the lifespan event in main.py. Raises RuntimeError on failure
so the process exits before accepting traffic.
"""

from __future__ import annotations

import base64
from pathlib import Path

from app.core.logging import get_logger
from app.core.settings import get_settings

log = get_logger("startup")


async def validate_all() -> None:
    """Run all startup checks. Raises RuntimeError on first failure."""
    settings = get_settings()
    await _check_redis(settings)
    _check_storage_paths(settings)
    _check_encryption_key(settings)
    log.info("startup.all_checks_passed")


async def _check_redis(settings) -> None:
    try:
        from app.core.redis import get_redis
        redis = get_redis()
        pong = await redis.ping()
        if not pong:
            raise RuntimeError("Redis ping returned falsy")
        log.info("startup.redis_ok")
    except Exception as exc:
        raise RuntimeError(f"Redis is unreachable: {exc}") from exc


def _check_storage_paths(settings) -> None:
    for label, path_str in (
        ("document_storage_path", settings.document_storage_path),
        ("report_storage_path", settings.report_storage_path),
    ):
        path = Path(path_str)
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RuntimeError(f"Cannot create {label} at {path_str}: {exc}") from exc

        # Verify the directory is writable
        probe = path / ".startup_probe"
        try:
            probe.write_text("ok")
            probe.unlink()
        except OSError as exc:
            raise RuntimeError(f"{label} at {path_str} is not writable: {exc}") from exc

    log.info("startup.storage_paths_ok")


def _check_encryption_key(settings) -> None:
    try:
        raw = base64.b64decode(settings.encryption_key)
        assert len(raw) == 32, f"expected 32 bytes, got {len(raw)}"
    except Exception as exc:
        raise RuntimeError(f"Invalid encryption_key: {exc}") from exc
    log.info("startup.encryption_key_ok")
