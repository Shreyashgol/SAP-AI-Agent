from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, field_validator


_RULE_TYPES = {"threshold", "anomaly", "business_event"}
_OPERATORS = {">", "<", "=", ">=", "<="}
_SEVERITIES = {"critical", "warning", "info"}
_SCHEDULES = {"hourly", "4hourly", "daily"}
_STATUSES = {"active", "acknowledged", "snoozed", "escalated"}


class AlertRuleCreate(BaseModel):
    name: str
    rule_type: str
    kpi_id: uuid.UUID | None = None
    operator: str | None = None
    threshold_value: float | None = None
    severity: str = "warning"
    assigned_role_ids: list[uuid.UUID] = []
    monitoring_schedule: str = "hourly"

    @field_validator("rule_type")
    @classmethod
    def validate_rule_type(cls, v: str) -> str:
        if v not in _RULE_TYPES:
            raise ValueError(f"rule_type must be one of {_RULE_TYPES}")
        return v

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        if v not in _SEVERITIES:
            raise ValueError(f"severity must be one of {_SEVERITIES}")
        return v

    @field_validator("monitoring_schedule")
    @classmethod
    def validate_schedule(cls, v: str) -> str:
        if v not in _SCHEDULES:
            raise ValueError(f"monitoring_schedule must be one of {_SCHEDULES}")
        return v

    @field_validator("operator")
    @classmethod
    def validate_operator(cls, v: str | None) -> str | None:
        if v is not None and v not in _OPERATORS:
            raise ValueError(f"operator must be one of {_OPERATORS}")
        return v


class AlertRulePatch(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    threshold_value: float | None = None
    severity: str | None = None
    monitoring_schedule: str | None = None


class AlertRuleResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    created_by: uuid.UUID
    kpi_id: uuid.UUID | None
    name: str
    rule_type: str
    operator: str | None
    threshold_value: float | None
    severity: str
    assigned_role_ids: list[Any]
    monitoring_schedule: str
    is_active: bool
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class AlertResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    alert_rule_id: uuid.UUID
    triggered_value: float | None
    expected_range: dict[str, Any] | None
    severity: str
    status: str
    acknowledged_by: uuid.UUID | None
    snoozed_until: str | None
    suggested_questions: list[Any] | None
    rca_summary: str | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class AlertAcknowledge(BaseModel):
    status: str  # "acknowledged" | "snoozed" | "escalated"
    snoozed_until: str | None = None  # ISO datetime string

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"acknowledged", "snoozed", "escalated"}
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return v
