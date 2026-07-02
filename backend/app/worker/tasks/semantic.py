"""
Celery tasks for semantic layer operations.

  semantic.apply_pack          — apply entity pack after discovery
  semantic.apply_erpref_prior  — warm-start a SAP B1 catalog with the ERPRef prior
  semantic.run_ai_mapping      — Claude AI mapping for unmapped tables
  semantic.seed_kpis           — seed system KPIs for a tenant
"""

from __future__ import annotations

from celery import Task

from app.core.logging import get_logger
from app.worker.celery_app import celery_app

log = get_logger(__name__)


@celery_app.task(
    bind=True,
    name="semantic.apply_pack",
    max_retries=2,
    default_retry_delay=30,
    queue="default",
)
def apply_entity_pack(
    self: Task,
    connection_id: str,
    tenant_id: str,
    db_type: str,
    schema_name: str | None = None,
) -> dict:
    """Apply the appropriate entity pack after a discovery job completes."""
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        _run_apply_pack(connection_id, tenant_id, db_type, schema_name)
    )


@celery_app.task(
    bind=True,
    name="semantic.apply_erpref_prior",
    max_retries=2,
    default_retry_delay=30,
    queue="default",
    soft_time_limit=300,
)
def apply_erpref_prior(
    self: Task,
    connection_id: str,
    tenant_id: str,
    schema_name: str | None = None,
) -> dict:
    """Warm-start the crawled catalog with the ERPRef prior (SAP B1 only)."""
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        _run_apply_erpref_prior(connection_id, tenant_id, schema_name)
    )


@celery_app.task(
    bind=True,
    name="semantic.run_ai_mapping",
    max_retries=2,
    default_retry_delay=60,
    queue="default",
    soft_time_limit=600,
)
def run_ai_mapping(
    self: Task,
    connection_id: str,
    tenant_id: str,
    limit: int = 50,
) -> dict:
    """Run Claude AI mapping for unmapped tables."""
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        _run_ai_mapping(connection_id, tenant_id, limit)
    )


@celery_app.task(
    name="semantic.seed_kpis",
    queue="default",
)
def seed_tenant_kpis(tenant_id: str) -> dict:
    """Seed system KPIs for a new tenant."""
    import asyncio
    return asyncio.get_event_loop().run_until_complete(_run_seed_kpis(tenant_id))


# ── Async implementations ──────────────────────────────────────────────────────

async def _run_apply_pack(
    connection_id: str, tenant_id: str, db_type: str, schema_name: str | None
) -> dict:
    import uuid
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy import select

    from app.core.settings import get_settings
    from app.models.connection import Connection
    from app.services.semantic.pack_loader import PackLoader
    from app.services.semantic.mssql_fingerprint import fingerprint_connection

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    conn_uuid = uuid.UUID(connection_id)
    tenant_uuid = uuid.UUID(tenant_id)

    try:
        async with Session() as db:
            if db_type == "hana":
                pack_source = "sap_b1"
            else:
                fp = await fingerprint_connection(db, tenant_uuid, conn_uuid, schema_name)
                pack_source = fp.pack_source
                log.info("semantic.pack.fingerprint", detected=fp.detected_erp,
                         confidence=fp.confidence)

            loader = PackLoader(db, tenant_uuid, conn_uuid, pack_source=pack_source)
            counts = await loader.apply(schema_name=schema_name)
            await db.commit()
            return {"status": "success", "pack_source": pack_source, "counts": counts}
    finally:
        await engine.dispose()


async def _run_apply_erpref_prior(
    connection_id: str, tenant_id: str, schema_name: str | None
) -> dict:
    import uuid
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core.settings import get_settings
    from app.services.semantic.erpref_prior import ErpRefPrior
    from app.services.semantic.mssql_fingerprint import fingerprint_connection

    settings = get_settings()
    if not settings.erpref_prior_enabled:
        return {"status": "skipped", "reason": "disabled"}

    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    conn_uuid = uuid.UUID(connection_id)
    tenant_uuid = uuid.UUID(tenant_id)

    try:
        async with Session() as db:
            # Gate: only warm-start a database that actually looks like SAP B1.
            fp = await fingerprint_connection(db, tenant_uuid, conn_uuid, schema_name)
            if fp.detected_erp != "sap_b1":
                log.info("erpref_prior.skip_non_b1",
                         detected=fp.detected_erp, confidence=round(fp.confidence, 3))
                return {"status": "skipped", "reason": "not_sap_b1",
                        "detected": fp.detected_erp}

            counts = await ErpRefPrior(db, tenant_uuid).apply(conn_uuid)
            await db.commit()
            log.info("erpref_prior.task.done", confidence=round(fp.confidence, 3), **counts)
            return {"status": "success", "detected": fp.detected_erp, **counts}
    finally:
        await engine.dispose()


async def _run_ai_mapping(connection_id: str, tenant_id: str, limit: int) -> dict:
    import uuid
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.core.settings import get_settings
    from app.services.semantic.ai_mapper import AIEntityMapper

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with Session() as db:
            mapper = AIEntityMapper(db, uuid.UUID(tenant_id))
            counts = await mapper.map_unmapped_tables(uuid.UUID(connection_id), limit=limit)
            await db.commit()
            return {"status": "success", **counts}
    finally:
        await engine.dispose()


async def _run_seed_kpis(tenant_id: str) -> dict:
    import uuid
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.core.settings import get_settings
    from app.services.semantic.kpi_library import seed_kpis

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with Session() as db:
            inserted = await seed_kpis(db, uuid.UUID(tenant_id))
            await db.commit()
            return {"status": "success", "kpis_inserted": inserted}
    finally:
        await engine.dispose()
