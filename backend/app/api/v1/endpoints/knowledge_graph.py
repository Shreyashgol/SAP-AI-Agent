"""
Knowledge Graph REST API — KG node/edge management and traversal.

Spec: KG-005, KG-006, KG-007, KG-008
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequirePlatformAdmin, RequirePowerUserOrAbove, get_current_tenant
from app.core.database import get_db
from app.models.knowledge_graph import KnowledgeGraphEdge, KnowledgeGraphNode
from app.models.semantic import SemanticEntity
from app.schemas.knowledge_graph import (
    EdgeConfirmRequest,
    EdgeResponse,
    KGBuildResponse,
    NodeResponse,
    TraversalResponse,
)
from app.services.knowledge_graph.traversal import GraphTraversal
from app.worker.tasks.knowledge_graph import build_full_kg

router = APIRouter(prefix="/knowledge-graph", tags=["knowledge-graph"])


@router.post(
    "/connections/{connection_id}/build",
    response_model=KGBuildResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[RequirePlatformAdmin],
)
async def trigger_kg_build(
    connection_id: uuid.UUID,
    tenant: Annotated[dict, Depends(get_current_tenant)],
):
    """Trigger a full KG rebuild for a connection (async)."""
    task = build_full_kg.delay(
        connection_id=str(connection_id),
        tenant_id=str(tenant["id"]),
        triggered_by="api",
    )
    return KGBuildResponse(job_id=task.id, status="queued")


@router.get(
    "/nodes",
    response_model=list[NodeResponse],
    dependencies=[RequirePowerUserOrAbove],
)
async def list_nodes(
    tenant: Annotated[dict, Depends(get_current_tenant)],
    connection_id: uuid.UUID | None = None,
    domain: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List KG nodes with optional filters."""
    q = select(KnowledgeGraphNode).where(
        KnowledgeGraphNode.tenant_id == tenant["id"]
    )
    if domain:
        q = q.where(KnowledgeGraphNode.domain == domain)

    if connection_id:
        # Filter nodes whose entity belongs to this connection
        from app.models.metadata import MetadataTable
        table_ids_q = select(MetadataTable.id).where(
            MetadataTable.connection_id == connection_id,
            MetadataTable.tenant_id == tenant["id"],
        )
        entity_ids_q = select(SemanticEntity.id).where(
            SemanticEntity.table_id.in_(table_ids_q)
        )
        q = q.where(KnowledgeGraphNode.entity_id.in_(entity_ids_q))

    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.get(
    "/edges",
    response_model=list[EdgeResponse],
    dependencies=[RequirePowerUserOrAbove],
)
async def list_edges(
    tenant: Annotated[dict, Depends(get_current_tenant)],
    unconfirmed_only: bool = False,
    from_node_id: uuid.UUID | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """List KG edges."""
    q = select(KnowledgeGraphEdge).where(
        KnowledgeGraphEdge.tenant_id == tenant["id"]
    )
    if unconfirmed_only:
        q = q.where(KnowledgeGraphEdge.is_admin_confirmed.is_(False))
    if from_node_id:
        q = q.where(KnowledgeGraphEdge.from_node_id == from_node_id)
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.patch(
    "/edges/{edge_id}/confirm",
    response_model=EdgeResponse,
    dependencies=[RequirePlatformAdmin],
)
async def confirm_edge(
    edge_id: uuid.UUID,
    body: EdgeConfirmRequest,
    tenant: Annotated[dict, Depends(get_current_tenant)],
    db: AsyncSession = Depends(get_db),
):
    """Admin confirms or rejects an inferred KG edge."""
    result = await db.execute(
        select(KnowledgeGraphEdge).where(
            KnowledgeGraphEdge.id == edge_id,
            KnowledgeGraphEdge.tenant_id == tenant["id"],
        )
    )
    edge = result.scalar_one_or_none()
    if not edge:
        raise HTTPException(status_code=404, detail="Edge not found")

    edge.is_admin_confirmed = body.confirmed
    await db.commit()
    await db.refresh(edge)
    return edge


@router.get(
    "/traverse",
    response_model=TraversalResponse,
    dependencies=[RequirePowerUserOrAbove],
)
async def traverse_path(
    from_entity_id: uuid.UUID,
    to_entity_id: uuid.UUID,
    tenant: Annotated[dict, Depends(get_current_tenant)],
    db: AsyncSession = Depends(get_db),
):
    """Find shortest join path between two entities."""
    traversal = GraphTraversal(db, tenant["id"])
    path = await traversal.find_path(from_entity_id, to_entity_id)
    join_sql = traversal.build_join_sql(path) if path.found else None
    return TraversalResponse(
        found=path.found,
        hop_count=path.hop_count,
        entity_chain=path.entity_chain(),
        join_sql=join_sql,
        steps=[
            {
                "from_entity": s.from_entity_name,
                "to_entity": s.to_entity_name,
                "join_condition": s.join_condition,
                "confidence": s.confidence,
                "edge_type": s.edge_type,
            }
            for s in path.steps
        ],
    )
