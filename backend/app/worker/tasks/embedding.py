"""
Celery tasks for embedding pipeline.

Spec: EM-004, EM-005, EM-006, TR-004
  - embedding.embed_tools        : embed all active tools for a tenant
  - embedding.embed_document     : chunk + embed a single document
  - embedding.embed_entities     : embed all semantic entities for a tenant
  - embedding.recalculate_weights: nightly tool ranking weight recalculation
"""

import uuid

from app.worker.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.worker.celery_app import celery_app

log = get_logger(__name__)


@celery_app.task(
    name="embedding.embed_tools",
    queue="default",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=300,
)
def embed_tools(tenant_id: str, force: bool = False) -> dict:
    """Embed all active tool descriptions for a tenant."""
    import asyncio
    return asyncio.run(_run_embed_tools(tenant_id, force))


@celery_app.task(
    name="embedding.embed_document",
    queue="default",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=600,
)
def embed_document(document_id: str, tenant_id: str) -> dict:
    """Chunk and embed a single uploaded document."""
    import asyncio
    return asyncio.run(_run_embed_document(document_id, tenant_id))


@celery_app.task(
    name="embedding.embed_entities",
    queue="default",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=300,
)
def embed_entities(tenant_id: str, force: bool = False) -> dict:
    """Embed all semantic entity descriptions for a tenant."""
    import asyncio
    return asyncio.run(_run_embed_entities(tenant_id, force))


@celery_app.task(
    name="tools.recalculate_weights",
    queue="default",
    max_retries=1,
)
def recalculate_tool_weights(tenant_id: str) -> dict:
    """Nightly: recalculate tool ranking weights from feedback + conversation history."""
    import asyncio
    return asyncio.run(_run_recalculate_weights(tenant_id))


# ── Async implementations ─────────────────────────────────────────────────────

async def _run_embed_tools(tenant_id: str, force: bool) -> dict:
    from app.services.embedding.tool_embedder import ToolEmbedder
    tenant_uuid = uuid.UUID(tenant_id)
    async with AsyncSessionLocal() as db:
        try:
            embedder = ToolEmbedder(db, tenant_uuid)
            result = await embedder.embed_all(force=force)
            await db.commit()
            log.info("embedding.embed_tools.done", tenant_id=tenant_id, **result)
            return {"status": "completed", **result}
        except Exception as exc:
            await db.rollback()
            log.error("embedding.embed_tools.error", tenant_id=tenant_id, exc=str(exc))
            raise


async def _run_embed_document(document_id: str, tenant_id: str) -> dict:
    from app.services.embedding.document_embedder import DocumentEmbedder
    tenant_uuid = uuid.UUID(tenant_id)
    doc_uuid = uuid.UUID(document_id)
    async with AsyncSessionLocal() as db:
        try:
            embedder = DocumentEmbedder(db, tenant_uuid)
            result = await embedder.process_document(doc_uuid)
            await db.commit()
            log.info("embedding.embed_document.done",
                     document_id=document_id, **result)
            return {"status": "completed", **result}
        except Exception as exc:
            await db.rollback()
            log.error("embedding.embed_document.error",
                      document_id=document_id, exc=str(exc))
            raise


async def _run_embed_entities(tenant_id: str, force: bool) -> dict:
    from app.services.embedding.semantic_embedder import SemanticEmbedder
    tenant_uuid = uuid.UUID(tenant_id)
    async with AsyncSessionLocal() as db:
        try:
            embedder = SemanticEmbedder(db, tenant_uuid)
            result = await embedder.embed_all(force=force)
            await db.commit()
            log.info("embedding.embed_entities.done", tenant_id=tenant_id, **result)
            return {"status": "completed", **result}
        except Exception as exc:
            await db.rollback()
            log.error("embedding.embed_entities.error", tenant_id=tenant_id, exc=str(exc))
            raise


async def _run_recalculate_weights(tenant_id: str) -> dict:
    from app.services.tools.ranker import ToolRanker
    tenant_uuid = uuid.UUID(tenant_id)
    async with AsyncSessionLocal() as db:
        try:
            ranker = ToolRanker(db, tenant_uuid)
            result = await ranker.update_weights()
            await db.commit()
            return {"status": "completed", **result}
        except Exception as exc:
            await db.rollback()
            log.error("recalculate_weights.error", tenant_id=tenant_id, exc=str(exc))
            raise
