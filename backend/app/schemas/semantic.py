"""Pydantic v2 schemas for the semantic layer API."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


# ── Entities ───────────────────────────────────────────────────────────────────

class EntityResponse(BaseModel):
    id: uuid.UUID
    table_id: uuid.UUID
    entity_name: str
    domain: str
    description: str | None
    is_ai_generated: bool
    is_human_override: bool
    confidence: float
    pack_source: str
    semantic_version: int


class EntityPatch(BaseModel):
    entity_name: str | None = None
    domain: str | None = None
    description: str | None = None


# ── Attributes ─────────────────────────────────────────────────────────────────

class AttributeResponse(BaseModel):
    id: uuid.UUID
    entity_id: uuid.UUID
    column_id: uuid.UUID
    attribute_name: str
    display_name: str
    semantic_type: str
    description: str | None
    is_human_override: bool
    is_ai_generated: bool


class AttributePatch(BaseModel):
    display_name: str | None = None
    semantic_type: str | None = None
    description: str | None = None


# ── KPIs ───────────────────────────────────────────────────────────────────────

class KPIResponse(BaseModel):
    id: uuid.UUID
    name: str
    display_name: str
    description: str | None
    formula: str | None
    unit: str | None
    aggregation_method: str
    display_format: str | None
    domain: str
    is_active: bool
    is_system: bool


class KPICreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    display_name: str = Field(..., min_length=2, max_length=255)
    description: str | None = None
    formula: str | None = None
    unit: str | None = None
    aggregation_method: str = "sum"
    display_format: str | None = None
    domain: str


class KPIPatch(BaseModel):
    display_name: str | None = None
    description: str | None = None
    formula: str | None = None
    is_active: bool | None = None


# ── Glossary ───────────────────────────────────────────────────────────────────

class GlossaryResponse(BaseModel):
    id: uuid.UUID
    term: str
    definition: str
    domain: str | None
    is_ai_generated: bool
    approved_by: uuid.UUID | None


class GlossaryCreate(BaseModel):
    term: str = Field(..., min_length=1, max_length=255)
    definition: str
    domain: str | None = None


class GlossaryPatch(BaseModel):
    definition: str | None = None
    domain: str | None = None


# ── Synonyms ───────────────────────────────────────────────────────────────────

class SynonymResponse(BaseModel):
    id: uuid.UUID
    synonym: str
    canonical_term: str
    entity_type: str


class SynonymCreate(BaseModel):
    synonym: str = Field(..., min_length=1, max_length=255)
    canonical_term: str = Field(..., min_length=1, max_length=255)
    entity_type: str = Field(..., pattern="^(metric|entity|attribute)$")


# ── Business Rules ─────────────────────────────────────────────────────────────

class BusinessRuleResponse(BaseModel):
    id: uuid.UUID
    entity_id: uuid.UUID
    rule_name: str
    predicate_sql: str
    description: str | None
    is_default: bool
    is_system: bool
    pack_source: str


class BusinessRuleCreate(BaseModel):
    rule_name: str = Field(..., min_length=2, max_length=255)
    predicate_sql: str
    description: str | None = None
    is_default: bool = False


class BusinessRulePatch(BaseModel):
    predicate_sql: str | None = None
    description: str | None = None
    is_default: bool | None = None


# ── AI Mapping / Pack ──────────────────────────────────────────────────────────

class ApplyPackRequest(BaseModel):
    connection_id: uuid.UUID
    schema_name: str | None = None


class ApplyPackResponse(BaseModel):
    job_id: str
    status: str
    pack_source: str | None = None


class AIMapRequest(BaseModel):
    connection_id: uuid.UUID
    limit: int = Field(default=50, ge=1, le=200)


class AIMapResponse(BaseModel):
    job_id: str
    status: str
