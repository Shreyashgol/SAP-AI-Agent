"""Pydantic schemas for document management endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    uploaded_by: uuid.UUID
    filename: str
    file_type: str
    file_size_bytes: int
    status: str
    chunk_count: int
    page_count: int | None
    document_type: str | None
    department: str | None
    linked_entity_ids: list[Any] | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentPatch(BaseModel):
    document_type: str | None = None
    department: str | None = None
    linked_entity_ids: list[uuid.UUID] | None = None
