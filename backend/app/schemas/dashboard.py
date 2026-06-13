from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, field_validator


class DashboardCreate(BaseModel):
    name: str
    is_shared: bool = False


class DashboardPatch(BaseModel):
    name: str | None = None
    is_shared: bool | None = None
    layout: dict[str, Any] | None = None


class DashboardResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    name: str
    is_shared: bool
    share_token: str | None
    layout: dict[str, Any] | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class WidgetCreate(BaseModel):
    conversation_turn_id: uuid.UUID
    title: str | None = None
    widget_type: str = "table"
    position_x: int = 0
    position_y: int = 0
    width: int = 4
    height: int = 3

    @field_validator("widget_type")
    @classmethod
    def validate_widget_type(cls, v: str) -> str:
        allowed = {"kpi_card", "bar", "line", "area", "donut", "waterfall", "table"}
        if v not in allowed:
            raise ValueError(f"widget_type must be one of {allowed}")
        return v


class WidgetPatch(BaseModel):
    title: str | None = None
    widget_type: str | None = None
    position_x: int | None = None
    position_y: int | None = None
    width: int | None = None
    height: int | None = None


class WidgetResponse(BaseModel):
    id: uuid.UUID
    dashboard_id: uuid.UUID
    conversation_turn_id: uuid.UUID
    title: str | None
    widget_type: str
    position_x: int
    position_y: int
    width: int
    height: int
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
