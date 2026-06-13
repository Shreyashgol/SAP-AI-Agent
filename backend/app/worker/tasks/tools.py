"""
Celery tasks for Tool generation.

  - tools.generate_for_connection: generate tools for all entities in a connection
  - tools.generate_kpi_tools: generate KPI tools for a tenant
  - tools.apply_tool_pack: seed SAP B1 tool pack
  - tools.deprecate_for_table: deprecate tools when a table schema changes
"""

import uuid

from app.worker.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.services.tools.generator import ToolGenerator
from app.services.tools.pack_loader import ToolPackLoader
from app.worker.celery_app import celery_app

log = get_logger(__name__)


@celery_app.task(
    name="tools.generate_for_connection",
    queue="default",
    max_retries=2,
    default_retry_delay=30,
)
def generate_tools_for_connection(connection_id: str, tenant_id: str) -> dict:
    import asyncio
    return asyncio.run(_run_generate_connection(connection_id, tenant_id))


@celery_app.task(
    name="tools.generate_kpi_tools",
    queue="default",
    max_retries=2,
)
def generate_kpi_tools(tenant_id: str) -> dict:
    import asyncio
    return asyncio.run(_run_generate_kpis(tenant_id))


@celery_app.task(
    name="tools.apply_tool_pack",
    queue="default",
    max_retries=2,
)
def apply_tool_pack(tenant_id: str, pack_source: str = "sap_b1") -> dict:
    import asyncio
    return asyncio.run(_run_apply_pack(tenant_id, pack_source))


@celery_app.task(
    name="tools.deprecate_for_table",
    queue="default",
)
def deprecate_tools_for_table(table_id: str, tenant_id: str) -> dict:
    import asyncio
    return asyncio.run(_run_deprecate_table(table_id, tenant_id))


# ── Async implementations ─────────────────────────────────────────────────────

async def _run_generate_connection(connection_id: str, tenant_id: str) -> dict:
    from sqlalchemy import select
    from app.models.metadata import MetadataTable
    from app.models.semantic import SemanticEntity

    tenant_uuid = uuid.UUID(tenant_id)
    conn_uuid = uuid.UUID(connection_id)

    async with AsyncSessionLocal() as db:
        try:
            tables_result = await db.execute(
                select(MetadataTable.id).where(
                    MetadataTable.connection_id == conn_uuid,
                    MetadataTable.tenant_id == tenant_uuid,
                )
            )
            table_ids = [r[0] for r in tables_result.fetchall()]

            entities_result = await db.execute(
                select(SemanticEntity.id).where(
                    SemanticEntity.tenant_id == tenant_uuid,
                    SemanticEntity.table_id.in_(table_ids),
                )
            )
            entity_ids = [r[0] for r in entities_result.fetchall()]

            generator = ToolGenerator(db, tenant_uuid)
            all_tools: list[str] = []
            for eid in entity_ids:
                tools = await generator.generate_for_entity(eid)
                all_tools.extend(tools)

            await db.commit()
            log.info("tools.generate_connection.done",
                     connection_id=connection_id, count=len(all_tools))
            return {"status": "completed", "tools_created": len(all_tools)}

        except Exception as exc:
            await db.rollback()
            log.error("tools.generate_connection.error",
                      connection_id=connection_id, exc=str(exc))
            raise


async def _run_generate_kpis(tenant_id: str) -> dict:
    tenant_uuid = uuid.UUID(tenant_id)
    async with AsyncSessionLocal() as db:
        try:
            generator = ToolGenerator(db, tenant_uuid)
            tools = await generator.generate_kpi_tools()
            await db.commit()
            return {"status": "completed", "tools_created": len(tools)}
        except Exception as exc:
            await db.rollback()
            log.error("tools.generate_kpis.error", tenant_id=tenant_id, exc=str(exc))
            raise


async def _run_apply_pack(tenant_id: str, pack_source: str) -> dict:
    tenant_uuid = uuid.UUID(tenant_id)
    async with AsyncSessionLocal() as db:
        try:
            loader = ToolPackLoader(db, tenant_uuid)
            result = await loader.apply(pack_source=pack_source)
            await db.commit()
            return {"status": "completed", **result}
        except Exception as exc:
            await db.rollback()
            log.error("tools.apply_pack.error", tenant_id=tenant_id, exc=str(exc))
            raise


async def _run_deprecate_table(table_id: str, tenant_id: str) -> dict:
    tenant_uuid = uuid.UUID(tenant_id)
    table_uuid = uuid.UUID(table_id)
    async with AsyncSessionLocal() as db:
        try:
            generator = ToolGenerator(db, tenant_uuid)
            count = await generator.deprecate_tools_for_table(table_uuid)
            await db.commit()
            return {"status": "completed", "deprecated_count": count}
        except Exception as exc:
            await db.rollback()
            log.error("tools.deprecate_table.error", table_id=table_id, exc=str(exc))
            raise
