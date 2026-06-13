"""Pydantic v2 schemas for discovery and metadata catalog endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class DiscoveryTriggerRequest(BaseModel):
    mode: str = Field(default="full", pattern="^(full|incremental)$")


class DiscoveryTriggerResponse(BaseModel):
    job_id: str
    mode: str
    status: str


class DiscoveryJobStatus(BaseModel):
    job_id: str
    stage: str  # starting | connecting | crawling | done | error
    pct: int    # 0-100
    detail: str = ""
    updated_at: str = ""


class CatalogTableSummary(BaseModel):
    id: uuid.UUID
    connection_id: uuid.UUID
    schema_name: str
    table_name: str
    object_type: str
    row_count_estimate: int | None
    is_pii_flagged: bool
    ai_description: str | None
    discovery_version: int


class CatalogTableDetail(CatalogTableSummary):
    metadata_hash: str | None
    columns: list[dict[str, Any]] = []


class CatalogTablePatch(BaseModel):
    ai_description: str | None = None
    is_pii_flagged: bool | None = None


class RelationResponse(BaseModel):
    id: uuid.UUID
    from_table_id: uuid.UUID
    from_column_id: uuid.UUID
    to_table_id: uuid.UUID
    to_column_id: uuid.UUID
    relation_type: str
    confidence: float
    is_admin_confirmed: bool
