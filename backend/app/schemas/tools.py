"""Pydantic v2 schemas for Tool Catalogue API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator


_VALID_CATEGORIES = {"aggregate", "entity_summary", "filter", "trend", "kpi", "join"}
_VALID_DOMAINS = {"finance", "sales", "purchasing", "inventory", "operations"}
_VALID_STATUSES = {"active", "deprecated", "draft"}


class ToolResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    category: str
    domain: str
    status: str
    version: int
    is_system: bool
    is_human_override: bool
    pack_source: str | None
    sql_template: str
    input_schema: list[dict[str, Any]]
    output_schema: dict[str, Any]
    permissions: dict[str, Any] | None
    last_validated_at: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ToolCreate(BaseModel):
    name: str
    description: str | None = None
    category: str
    domain: str
    sql_template: str
    input_schema: list[dict[str, Any]] = []
    output_schema: dict[str, Any] = {}
    permissions: dict[str, Any] | None = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in _VALID_CATEGORIES:
            raise ValueError(f"category must be one of {_VALID_CATEGORIES}")
        return v

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        if v not in _VALID_DOMAINS:
            raise ValueError(f"domain must be one of {_VALID_DOMAINS}")
        return v


class ToolPatch(BaseModel):
    description: str | None = None
    sql_template: str | None = None
    input_schema: list[dict[str, Any]] | None = None
    output_schema: dict[str, Any] | None = None
    status: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_STATUSES:
            raise ValueError(f"status must be one of {_VALID_STATUSES}")
        return v


class ToolPackApplyResponse(BaseModel):
    job_id: str
    status: str
    pack_source: str
