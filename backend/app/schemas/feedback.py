"""Pydantic schemas for user feedback endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class FeedbackCreate(BaseModel):
    conversation_turn_id: uuid.UUID
    tool_id: uuid.UUID | None = None
    rating: int = Field(..., description="1 = thumbs up, -1 = thumbs down")

    @field_validator("rating")
    @classmethod
    def rating_must_be_valid(cls, v: int) -> int:
        if v not in (1, -1):
            raise ValueError("rating must be 1 (thumbs up) or -1 (thumbs down)")
        return v


class FeedbackResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    conversation_turn_id: uuid.UUID
    tool_id: uuid.UUID | None
    rating: int
    created_at: datetime

    model_config = {"from_attributes": True}


class CorrectionCreate(BaseModel):
    conversation_turn_id: uuid.UUID
    correction_text: str = Field(..., min_length=10, max_length=5000)


class CorrectionResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    conversation_turn_id: uuid.UUID
    correction_text: str
    admin_status: str
    created_at: datetime

    model_config = {"from_attributes": True}
