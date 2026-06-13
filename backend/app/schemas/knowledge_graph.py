"""Pydantic v2 schemas for Knowledge Graph API."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel


class NodeResponse(BaseModel):
    id: uuid.UUID
    entity_id: uuid.UUID
    node_label: str
    domain: str | None
    node_properties: dict[str, Any] | None

    model_config = {"from_attributes": True}


class EdgeResponse(BaseModel):
    id: uuid.UUID
    from_node_id: uuid.UUID
    to_node_id: uuid.UUID
    relation_name: str
    edge_type: str
    confidence: float
    is_admin_confirmed: bool
    join_condition: str | None

    model_config = {"from_attributes": True}


class EdgeConfirmRequest(BaseModel):
    confirmed: bool


class KGBuildResponse(BaseModel):
    job_id: str
    status: str


class TraversalStep(BaseModel):
    from_entity: str
    to_entity: str
    join_condition: str
    confidence: float
    edge_type: str


class TraversalResponse(BaseModel):
    found: bool
    hop_count: int
    entity_chain: list[str]
    join_sql: str | None
    steps: list[TraversalStep]
