"""Pydantic schemas for Conversation and ConversationTurn endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Conversation ─────────────────────────────────────────────────────────────

class ConversationCreate(BaseModel):
    title: str | None = None
    connection_id: uuid.UUID | None = None


class ConversationResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    title: str | None
    is_active: bool
    turn_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Ask request / response ────────────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=2000)
    connection_id: uuid.UUID | None = None


class AskResponse(BaseModel):
    turn_id: uuid.UUID
    conversation_id: uuid.UUID
    question: str
    answer_text: str | None
    answer_data: dict[str, Any] | None
    sql_query: str | None
    chart_hint: str | None
    follow_up_questions: list[str]
    lineage: dict[str, Any] | None
    confidence_score: float | None
    execution_time_ms: int | None
    agents_invoked: list[str]
    intent: str | None
    has_error: bool
    error_message: str | None
    # Clarification fields (AG-007)
    needs_clarification: bool = False
    clarification_question: str | None = None
    missing_params: list[str] = []


# ── Turn ─────────────────────────────────────────────────────────────────────

class TurnResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    turn_number: int
    question: str
    answer_text: str | None
    answer_data: dict[str, Any] | None
    sql_query: str | None
    chart_hint: str | None
    follow_up_questions: list[str] | None
    lineage: dict[str, Any] | None
    confidence_score: float | None
    execution_time_ms: int | None
    agents_invoked: list[str] | None
    intent: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
