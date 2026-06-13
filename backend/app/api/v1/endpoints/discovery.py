"""
Discovery API endpoints.

POST  /connections/{id}/discover        — trigger full or incremental discovery job
GET   /connections/{id}/discover/status — poll job progress from Redis
GET   /catalog/tables                   — paginated metadata catalog with search
GET   /catalog/tables/{id}              — table detail with columns + relations
PATCH /catalog/tables/{id}              — update AI description / un-flag PII
GET   /catalog/relations                — list all inferred relations for tenant
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from app.core.deps import CurrentUser, RequirePlatformAdmin, RequirePowerUserOrAbove, get_redis
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.connection import Connection
from app.models.metadata import MetadataColumn, MetadataRelation, MetadataTable
from app.schemas.base import APIResponse, PaginatedResponse
from app.schemas.discovery import (
    CatalogTableDetail,
    CatalogTablePatch,
    CatalogTableSummary,
    DiscoveryJobStatus,
    DiscoveryTriggerRequest,
    DiscoveryTriggerResponse,
    RelationResponse,
)

router = APIRouter(tags=["discovery"])
log = get_logger(__name__)


# ── Trigger discovery ──────────────────────────────────────────────────────────

@router.post(
    "/connections/{connection_id}/discover",
    response_model=APIResponse[DiscoveryTriggerResponse],
    dependencies=[RequirePlatformAdmin],
)
async def trigger_discovery(
    connection_id: uuid.UUID,
    body: DiscoveryTriggerRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[DiscoveryTriggerResponse]:
    result = await db.execute(
        select(Connection).where(
            Connection.id == connection_id,
            Connection.tenant_id == current_user.tenant_id,
            Connection.is_active.is_(True),
        )
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise NotFoundError("Connection")

    from app.worker.tasks.discovery import run_full_discovery, run_incremental_discovery

    mode = body.mode or "full"
    task_fn = run_full_discovery if mode == "full" else run_incremental_discovery
    task = task_fn.delay(
        connection_id=str(connection_id),
        tenant_id=str(current_user.tenant_id),
        triggered_by=str(current_user.id),
    )

    log.info("discovery.triggered", mode=mode, connection_id=str(connection_id),
             job_id=task.id)

    return APIResponse(
        success=True,
        data=DiscoveryTriggerResponse(job_id=task.id, mode=mode, status="queued"),
    )


# ── Job status ────────────────────────────────────────────────────────────────

@router.get(
    "/connections/{connection_id}/discover/status",
    response_model=APIResponse[DiscoveryJobStatus],
    dependencies=[RequirePowerUserOrAbove],
)
async def get_discovery_status(
    connection_id: uuid.UUID,
    job_id: str,
    current_user: CurrentUser,
    redis: aioredis.Redis = Depends(get_redis),
) -> APIResponse[DiscoveryJobStatus]:
    from app.worker.tasks.discovery import _progress_key
    raw = await redis.get(_progress_key(job_id))
    if not raw:
        raise HTTPException(status_code=404, detail="Job not found or expired.")
    data = json.loads(raw)
    return APIResponse(success=True, data=DiscoveryJobStatus(job_id=job_id, **data))


# ── Catalog — table list ──────────────────────────────────────────────────────

@router.get(
    "/catalog/tables",
    response_model=PaginatedResponse[CatalogTableSummary],
    dependencies=[RequirePowerUserOrAbove],
)
async def list_catalog_tables(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    search: str | None = Query(None, description="Full-text search"),
    connection_id: uuid.UUID | None = Query(None),
    schema_name: str | None = Query(None),
    pii_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> PaginatedResponse[CatalogTableSummary]:
    q = select(MetadataTable).where(MetadataTable.tenant_id == current_user.tenant_id)

    if connection_id:
        q = q.where(MetadataTable.connection_id == connection_id)
    if schema_name:
        q = q.where(MetadataTable.schema_name == schema_name)
    if pii_only:
        q = q.where(MetadataTable.is_pii_flagged.is_(True))
    if search:
        # tsvector search if populated, fallback to ILIKE
        q = q.where(
            or_(
                MetadataTable.table_name.ilike(f"%{search}%"),
                MetadataTable.ai_description.ilike(f"%{search}%"),
            )
        )

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    rows_result = await db.execute(
        q.order_by(MetadataTable.schema_name, MetadataTable.table_name)
         .offset(offset)
         .limit(page_size)
    )
    tables = rows_result.scalars().all()

    return PaginatedResponse(
        success=True,
        data=[
            CatalogTableSummary(
                id=t.id,
                connection_id=t.connection_id,
                schema_name=t.schema_name,
                table_name=t.table_name,
                object_type=t.object_type,
                row_count_estimate=t.row_count_estimate,
                is_pii_flagged=t.is_pii_flagged,
                ai_description=t.ai_description,
                discovery_version=t.discovery_version,
            )
            for t in tables
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── Catalog — table detail ────────────────────────────────────────────────────

@router.get(
    "/catalog/tables/{table_id}",
    response_model=APIResponse[CatalogTableDetail],
    dependencies=[RequirePowerUserOrAbove],
)
async def get_catalog_table(
    table_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[CatalogTableDetail]:
    result = await db.execute(
        select(MetadataTable).where(
            MetadataTable.id == table_id,
            MetadataTable.tenant_id == current_user.tenant_id,
        )
    )
    table = result.scalar_one_or_none()
    if not table:
        raise NotFoundError("Table")

    cols_result = await db.execute(
        select(MetadataColumn)
        .where(MetadataColumn.table_id == table_id)
        .order_by(MetadataColumn.ordinal_position)
    )
    columns = cols_result.scalars().all()

    return APIResponse(
        success=True,
        data=CatalogTableDetail(
            id=table.id,
            connection_id=table.connection_id,
            schema_name=table.schema_name,
            table_name=table.table_name,
            object_type=table.object_type,
            row_count_estimate=table.row_count_estimate,
            is_pii_flagged=table.is_pii_flagged,
            ai_description=table.ai_description,
            discovery_version=table.discovery_version,
            metadata_hash=table.metadata_hash,
            columns=[
                {
                    "id": str(c.id),
                    "column_name": c.column_name,
                    "data_type": c.data_type,
                    "is_nullable": c.is_nullable,
                    "is_primary_key": c.is_primary_key,
                    "is_foreign_key": c.is_foreign_key,
                    "is_pii_flagged": c.is_pii_flagged,
                    "is_masked": c.is_masked,
                    "ai_description": c.ai_description,
                    "ordinal_position": c.ordinal_position,
                    "sample_values": c.sample_values,
                    "column_stats": c.column_stats,
                }
                for c in columns
            ],
        ),
    )


# ── Catalog — update table metadata ──────────────────────────────────────────

@router.patch(
    "/catalog/tables/{table_id}",
    response_model=APIResponse[CatalogTableSummary],
    dependencies=[RequirePlatformAdmin],
)
async def patch_catalog_table(
    table_id: uuid.UUID,
    body: CatalogTablePatch,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[CatalogTableSummary]:
    result = await db.execute(
        select(MetadataTable).where(
            MetadataTable.id == table_id,
            MetadataTable.tenant_id == current_user.tenant_id,
        )
    )
    table = result.scalar_one_or_none()
    if not table:
        raise NotFoundError("Table")

    if body.ai_description is not None:
        table.ai_description = body.ai_description
    if body.is_pii_flagged is not None:
        table.is_pii_flagged = body.is_pii_flagged

    await db.commit()
    await db.refresh(table)

    return APIResponse(
        success=True,
        data=CatalogTableSummary(
            id=table.id,
            connection_id=table.connection_id,
            schema_name=table.schema_name,
            table_name=table.table_name,
            object_type=table.object_type,
            row_count_estimate=table.row_count_estimate,
            is_pii_flagged=table.is_pii_flagged,
            ai_description=table.ai_description,
            discovery_version=table.discovery_version,
        ),
    )


# ── Catalog — relations ───────────────────────────────────────────────────────

@router.get(
    "/catalog/relations",
    response_model=PaginatedResponse[RelationResponse],
    dependencies=[RequirePowerUserOrAbove],
)
async def list_relations(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    connection_id: uuid.UUID | None = Query(None),
    unconfirmed_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[RelationResponse]:
    q = select(MetadataRelation).where(MetadataRelation.tenant_id == current_user.tenant_id)
    if unconfirmed_only:
        q = q.where(MetadataRelation.is_admin_confirmed.is_(False))

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_result.scalar_one()

    rows_result = await db.execute(
        q.order_by(MetadataRelation.confidence.desc())
         .offset((page - 1) * page_size)
         .limit(page_size)
    )
    relations = rows_result.scalars().all()

    return PaginatedResponse(
        success=True,
        data=[
            RelationResponse(
                id=r.id,
                from_table_id=r.from_table_id,
                from_column_id=r.from_column_id,
                to_table_id=r.to_table_id,
                to_column_id=r.to_column_id,
                relation_type=r.relation_type,
                confidence=r.confidence,
                is_admin_confirmed=r.is_admin_confirmed,
            )
            for r in relations
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
