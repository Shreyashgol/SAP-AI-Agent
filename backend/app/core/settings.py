import base64
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env from the project root (two levels up from this file: app/core/settings.py)
_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_env: Literal["development", "staging", "production"] = "development"
    app_secret_key: str = Field(..., min_length=32)
    debug: bool = False
    # Echo every SQL statement to the logs. Off by default even in debug —
    # it drowns out the agent-flow logs. Set SQL_ECHO=true only when
    # debugging the database layer specifically.
    sql_echo: bool = False

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "sap_ai_platform"
    postgres_user: str
    postgres_password: str

    # ── Redis ────────────────────────────────────────────────────────────────
    redis_url: str = "redis://redis:6379/0"
    redis_session_db: int = 1
    redis_cache_db: int = 2

    # ── Celery ───────────────────────────────────────────────────────────────
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/0"

    # ── Claude API ───────────────────────────────────────────────────────────
    anthropic_api_key: str
    anthropic_default_model: str = "claude-sonnet-4-6"
    anthropic_fast_model: str = "claude-haiku-4-5-20251001"

    # ── LangSmith ────────────────────────────────────────────────────────────
    langsmith_api_key: str = ""
    langsmith_project: str = "sap-ai-platform"
    langchain_tracing_v2: bool = False

    # ── Sentry ───────────────────────────────────────────────────────────────
    sentry_dsn: str = ""

    # ── JWT ──────────────────────────────────────────────────────────────────
    jwt_secret_key: str = Field(..., min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_hours: int = 8
    jwt_refresh_token_expire_days: int = 30

    # ── Encryption ───────────────────────────────────────────────────────────
    encryption_key: str  # AES-256, base64-encoded 32-byte key

    # ── Rate Limiting ────────────────────────────────────────────────────────
    rate_limit_per_user: int = 60    # req/min
    rate_limit_per_tenant: int = 100  # req/min

    # ── CORS ─────────────────────────────────────────────────────────────────
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v: str | list) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    # ── File Storage ─────────────────────────────────────────────────────────
    document_storage_path: str = "/data/documents"
    report_storage_path: str = "/data/reports"
    # Max upload size: 50 MB
    max_file_size_bytes: int = 50 * 1024 * 1024
    allowed_document_extensions: list[str] = ["pdf", "docx", "txt", "md", "markdown"]

    # ── Observability ────────────────────────────────────────────────────────
    metrics_enabled: bool = True
    # Prometheus metrics endpoint: /metrics (protected in production by network policy)
    health_check_timeout_seconds: float = 5.0

    # ── Security ─────────────────────────────────────────────────────────────
    # Additional HSTS max-age in seconds (production only)
    hsts_max_age: int = 31_536_000  # 1 year

    @model_validator(mode="after")
    def validate_encryption_key(self) -> "Settings":
        """Fail fast if encryption_key is not a valid 32-byte base64 value."""
        try:
            raw = base64.b64decode(self.encryption_key)
            if len(raw) != 32:
                raise ValueError(
                    f"encryption_key must decode to exactly 32 bytes (AES-256); "
                    f"got {len(raw)} bytes"
                )
        except Exception as exc:
            raise ValueError(f"Invalid encryption_key: {exc}") from exc
        return self

    @model_validator(mode="after")
    def warn_debug_in_production(self) -> "Settings":
        if self.is_production and self.debug:
            raise ValueError("debug=True must not be set in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
