from __future__ import annotations

import re
import uuid
from typing import Any

from pydantic import BaseModel, field_validator

# Validate cron expressions — simple 5-field format
_CRON_FIELD = r"(\*(?:/[0-9]+)?|[0-9,\-/]+)"
_CRON_RE = re.compile(
    rf"^{_CRON_FIELD}\s+"  # minute
    rf"{_CRON_FIELD}\s+"  # hour
    rf"{_CRON_FIELD}\s+"  # day-of-month
    rf"{_CRON_FIELD}\s+"  # month
    rf"{_CRON_FIELD}$"  # day-of-week
)


class ReportScheduleCreate(BaseModel):
    name: str
    questions: list[str]
    cron_expression: str
    delivery_channels: dict[str, Any] = {}
    subscriber_ids: list[uuid.UUID] = []

    @field_validator("questions")
    @classmethod
    def at_least_one_question(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one question is required")
        return v

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        if not _CRON_RE.match(v.strip()):
            raise ValueError(f"Invalid cron expression: {v!r}")
        return v.strip()


class ReportSchedulePatch(BaseModel):
    name: str | None = None
    questions: list[str] | None = None
    cron_expression: str | None = None
    delivery_channels: dict[str, Any] | None = None
    is_active: bool | None = None


class ReportScheduleResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    created_by: uuid.UUID
    name: str
    questions: list[str]
    cron_expression: str
    delivery_channels: dict[str, Any]
    is_active: bool
    subscriber_ids: list[Any]
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class ReportExecutionResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    schedule_id: uuid.UUID
    status: str
    storage_path: str | None
    error_message: str | None
    delivered_at: str | None
    execution_time_ms: int | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
