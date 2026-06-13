"""
Celery tasks for Knowledge Graph build/refresh.

Spec: KG-008, KG-009
  - kg.build_full: full rebuild after discovery completes
  - kg.build_for_entity: single-entity refresh triggered by catalog change
"""

import uuid
from datetime import UTC, datetime

from celery import Task

from app.worker.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.services.knowledge_graph.builder import KnowledgeGraphBuilder
from app.worker.celery_app import celery_app

log = get_logger(__name__)


class _BaseKGTask(Task):
    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        log.error("kg.task.failed", task_id=task_id, exc=str(exc))


@celery_app.task(
    bind=True,
    base=_BaseKGTask,
    name="kg.build_full",
    queue="default",
    max_retries=2,
    default_retry_delay=30,
)
def build_full_kg(
    self,
    connection_id: str,
    tenant_id: str,
    triggered_by: str = "system",
) -> dict:
    """Perform a full KG rebuild for a connection after discovery."""
    import asyncio
    return asyncio.run(_run_build_full(self, connection_id, tenant_id, triggered_by))


@celery_app.task(
    bind=True,
    base=_BaseKGTask,
    name="kg.build_for_entity",
    queue="default",
    max_retries=2,
    default_retry_delay=15,
)
def build_kg_for_entity(
    self,
    entity_id: str,
    connection_id: str,
    tenant_id: str,
) -> dict:
    """Refresh KG for a single entity after catalog change (KG-009)."""
    import asyncio
    return asyncio.run(_run_build_for_entity(self, entity_id, connection_id, tenant_id))


# ── Async implementations ─────────────────────────────────────────────────────

async def _run_build_full(task: Task, connection_id: str, tenant_id: str, triggered_by: str) -> dict:
    conn_uuid = uuid.UUID(connection_id)
    tenant_uuid = uuid.UUID(tenant_id)
    started_at = datetime.now(UTC).isoformat()

    log.info("kg.build_full.start",
             connection_id=connection_id, tenant_id=tenant_id,
             triggered_by=triggered_by)

    async with AsyncSessionLocal() as db:
        try:
            builder = KnowledgeGraphBuilder(db, tenant_uuid, conn_uuid)
            result = await builder.build_full()
            await db.commit()

            log.info("kg.build_full.done",
                     connection_id=connection_id,
                     nodes=result["nodes"],
                     edges_explicit=result["edges_explicit"],
                     edges_inferred=result["edges_inferred"])

            return {
                "status": "completed",
                "connection_id": connection_id,
                "started_at": started_at,
                "completed_at": datetime.now(UTC).isoformat(),
                **result,
            }

        except Exception as exc:
            await db.rollback()
            log.error("kg.build_full.error", connection_id=connection_id, exc=str(exc))
            raise task.retry(exc=exc)


async def _run_build_for_entity(
    task: Task, entity_id: str, connection_id: str, tenant_id: str
) -> dict:
    entity_uuid = uuid.UUID(entity_id)
    conn_uuid = uuid.UUID(connection_id)
    tenant_uuid = uuid.UUID(tenant_id)

    log.info("kg.build_entity.start", entity_id=entity_id, connection_id=connection_id)

    async with AsyncSessionLocal() as db:
        try:
            builder = KnowledgeGraphBuilder(db, tenant_uuid, conn_uuid)
            await builder.refresh_for_entity(entity_uuid)
            await db.commit()

            log.info("kg.build_entity.done", entity_id=entity_id)
            return {"status": "completed", "entity_id": entity_id}

        except Exception as exc:
            await db.rollback()
            log.error("kg.build_entity.error", entity_id=entity_id, exc=str(exc))
            raise task.retry(exc=exc)
