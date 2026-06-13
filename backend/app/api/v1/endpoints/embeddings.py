"""
Embedding Pipeline REST API.

Spec: EM-004, EM-005, EM-006
- POST /embeddings/tools        : trigger tool embedding for tenant
- POST /embeddings/entities     : trigger entity embedding
- POST /embeddings/documents/{id}: trigger single document embedding
- GET  /embeddings/search/tools : semantic tool search (used by UI + agents)
- GET  /embeddings/search/entities : semantic entity search
- POST /tools/custom-builder    : NL → SQL tool generation
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequirePlatformAdmin, RequirePowerUserOrAbove, get_current_tenant
from app.core.database import get_db
from app.services.embedding.vector_search import VectorSearchService
from app.worker.tasks.embedding import embed_document, embed_entities, embed_tools

router = APIRouter(prefix="/embeddings", tags=["embeddings"])


# ── Trigger actions ───────────────────────────────────────────────────────────

class EmbedJobResponse(BaseModel):
    job_id: str
    status: str
    target: str


@router.post(
    "/tools",
    response_model=EmbedJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[RequirePlatformAdmin],
)
async def trigger_embed_tools(
    tenant: Annotated[dict, Depends(get_current_tenant)],
    force: bool = False,
):
    """Trigger background embedding of all active tools for the tenant."""
    task = embed_tools.delay(tenant_id=str(tenant["id"]), force=force)
    return EmbedJobResponse(job_id=task.id, status="queued", target="tools")


@router.post(
    "/entities",
    response_model=EmbedJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[RequirePlatformAdmin],
)
async def trigger_embed_entities(
    tenant: Annotated[dict, Depends(get_current_tenant)],
    force: bool = False,
):
    """Trigger background embedding of all semantic entities for the tenant."""
    task = embed_entities.delay(tenant_id=str(tenant["id"]), force=force)
    return EmbedJobResponse(job_id=task.id, status="queued", target="entities")


@router.post(
    "/documents/{document_id}",
    response_model=EmbedJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[RequirePlatformAdmin],
)
async def trigger_embed_document(
    document_id: uuid.UUID,
    tenant: Annotated[dict, Depends(get_current_tenant)],
):
    """Trigger chunking and embedding for a single uploaded document."""
    task = embed_document.delay(
        document_id=str(document_id),
        tenant_id=str(tenant["id"]),
    )
    return EmbedJobResponse(
        job_id=task.id, status="queued", target=f"document:{document_id}"
    )


# ── Semantic search ───────────────────────────────────────────────────────────

class ToolSearchResult(BaseModel):
    tool_id: uuid.UUID
    tool_name: str
    description: str | None
    domain: str
    category: str
    similarity: float


class EntitySearchResult(BaseModel):
    entity_id: uuid.UUID
    entity_name: str
    domain: str
    similarity: float


@router.get(
    "/search/tools",
    response_model=list[ToolSearchResult],
    dependencies=[RequirePowerUserOrAbove],
)
async def search_tools(
    q: str = Query(..., min_length=2, description="Natural-language query"),
    domain: str | None = None,
    top_k: int = Query(10, ge=1, le=50),
    tenant: Annotated[dict, Depends(get_current_tenant)] = None,
    db: AsyncSession = Depends(get_db),
):
    """Semantic search over tool catalogue."""
    search = VectorSearchService(db, tenant["id"])
    results = await search.find_tools(q, top_k=top_k, domain=domain)
    return [
        ToolSearchResult(
            tool_id=r.tool_id,
            tool_name=r.tool_name,
            description=r.description,
            domain=r.domain,
            category=r.category,
            similarity=r.similarity,
        )
        for r in results
    ]


@router.get(
    "/search/entities",
    response_model=list[EntitySearchResult],
    dependencies=[RequirePowerUserOrAbove],
)
async def search_entities(
    q: str = Query(..., min_length=2, description="Natural-language query"),
    top_k: int = Query(10, ge=1, le=50),
    tenant: Annotated[dict, Depends(get_current_tenant)] = None,
    db: AsyncSession = Depends(get_db),
):
    """Semantic search over semantic entity catalogue."""
    search = VectorSearchService(db, tenant["id"])
    results = await search.find_entities(q, top_k=top_k)
    return [
        EntitySearchResult(
            entity_id=r.entity_id,
            entity_name=r.entity_name,
            domain=r.domain,
            similarity=r.similarity,
        )
        for r in results
    ]
