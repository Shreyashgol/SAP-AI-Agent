"""
Celery discovery tasks — full and incremental schema crawl.

Task flow:
  1. Load connection from DB, decrypt credentials
  2. Open source-DB connection (HANA / MSSQL) via connector
  3. Run SchemaCrawler.run_full() or run_incremental()
  4. Update connection health status
  5. Emit audit log entry

Progress is tracked in Redis at:  discovery:progress:{job_id}
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from celery import Task

from app.core.encryption import decrypt
from app.core.logging import get_logger
from app.services.audit_service import AuditEvent
from app.worker.celery_app import celery_app

log = get_logger(__name__)

# ── Progress key ──────────────────────────────────────────────────────────────

def _progress_key(job_id: str) -> str:
    return f"discovery:progress:{job_id}"


# ── Post-discovery pipeline ───────────────────────────────────────────────────

def build_post_discovery_pipeline(
    connection_id: str,
    tenant_id: str,
    db_type: str,
    include_knowledge_graph: bool = False,
):
    """
    Intelligence pipeline that follows a successful schema crawl.

    The only strict dependency is Database → Discovery → Metadata (already
    done by the caller). Everything after is enrichment:

        Phase A   Metadata Catalog (crawler output, already stored)
                       │
        Foundation     Entity Pack → first entity-embedding pass
                       │            (chat gains basic DB understanding here)
            ┌──────────┼──────────┐
        Phase B    AI Metadata │ KPI Engine │ Tool Engine     (parallel
            └──────────┼──────────┘          independent engines)
                       │
        Phase C    Embedding Engine → pgvector                (parallel pair)
                       │
        Phase D    Chat Runtime fully enriched

    Ordering exists only *inside* an engine, on its own data (KPI tools
    after KPI seed; connection tools after the static pack). The knowledge
    graph is out of the MVP pipeline (include_knowledge_graph=False);
    build it later via POST /knowledge-graph/build or flip the flag.
    Document processing is per-upload (embedding.embed_document) and never
    part of this pipeline. All signatures are immutable (.si); each task
    keeps its own retry policy; any stage can be re-run via its admin
    endpoint.
    """
    from celery import chain, group

    from app.core.settings import get_settings
    from app.worker.tasks.embedding import embed_entities, embed_tools
    from app.worker.tasks.semantic import (
        apply_entity_pack,
        run_ai_mapping,
        seed_tenant_kpis,
    )
    from app.worker.tasks.tools import (
        apply_tool_pack,
        generate_ai_collection,
        generate_kpi_tools,
        generate_tools_for_connection,
    )

    # AI-driven path: Claude builds the entire semantic layer from the REAL crawled
    # schema. Entities come from run_ai_mapping (no pack applied → all tables are
    # unmapped, so it maps them all); KPIs + tools come from generate_ai_collection,
    # which validates every generated SQL against the crawled catalog. This avoids
    # the static SAP B1 pack's assumption of columns that may not exist.
    if get_settings().onboarding_ai_generation:
        return chain(
            run_ai_mapping.si(connection_id, tenant_id),
            embed_entities.si(tenant_id),
            generate_ai_collection.si(connection_id, tenant_id),
            group(
                embed_entities.si(tenant_id),
                embed_tools.si(tenant_id),
            ),
        )

    # Pack fallback (no LLM): deterministic SAP B1 pack + template tools.
    # Phase B — independent enrichment engines, one branch per engine
    engines = [
        # AI Metadata Engine: Claude maps tables the pack didn't cover
        run_ai_mapping.si(connection_id, tenant_id),
        # KPI Engine: seed library, then one tool per KPI
        chain(
            seed_tenant_kpis.si(tenant_id),
            generate_kpi_tools.si(tenant_id),
        ),
        # Tool Engine: static pack, then entity summary / drill-down tools
        chain(
            apply_tool_pack.si(tenant_id),
            generate_tools_for_connection.si(connection_id, tenant_id),
        ),
    ]
    if include_knowledge_graph:
        from app.worker.tasks.knowledge_graph import build_full_kg

        engines.append(
            build_full_kg.si(connection_id, tenant_id, triggered_by="discovery")
        )

    return chain(
        # Foundation: deterministic ERP-pack mapping (fast, no LLM) and an
        # early embedding pass so chat works before enrichment finishes
        apply_entity_pack.si(connection_id, tenant_id, db_type),
        embed_entities.si(tenant_id),
        # Phase B — parallel workers
        group(*engines),
        # Phase C — final embedding pass picks up everything Phase B produced
        group(
            embed_entities.si(tenant_id),
            embed_tools.si(tenant_id),
        ),
    )


# ── Task base with async DB/Redis setup ───────────────────────────────────────

class DiscoveryTask(Task):
    abstract = True


# ── Full discovery ─────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    base=DiscoveryTask,
    name="discovery.run_full",
    max_retries=2,
    default_retry_delay=60,
    queue="discovery",
)
def run_full_discovery(
    self: Task,
    connection_id: str,
    tenant_id: str,
    triggered_by: str,
) -> dict:
    """
    Full schema discovery for a connection.
    Enqueued by POST /connections/{id}/discover or Redbeat schedule.
    """
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        _execute_discovery(self, connection_id, tenant_id, triggered_by, mode="full")
    )


@celery_app.task(
    bind=True,
    base=DiscoveryTask,
    name="discovery.run_incremental",
    max_retries=3,
    default_retry_delay=300,
    queue="discovery",
)
def run_incremental_discovery(
    self: Task,
    connection_id: str,
    tenant_id: str,
    triggered_by: str = "scheduler",
) -> dict:
    """
    Incremental discovery — only tables whose metadata_hash changed.
    Scheduled daily via RedBeat.
    """
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        _execute_discovery(self, connection_id, tenant_id, triggered_by, mode="incremental")
    )


# ── Shared execution logic ────────────────────────────────────────────────────

async def _execute_discovery(
    task: Task,
    connection_id: str,
    tenant_id: str,
    triggered_by: str,
    mode: str,
) -> dict:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    import redis.asyncio as aioredis

    from app.core.settings import get_settings
    from app.models.connection import Connection
    from app.services.audit_service import AuditService
    from app.services.discovery.crawler import SchemaCrawler
    from sqlalchemy import select

    settings = get_settings()
    job_id = task.request.id or str(uuid.uuid4())
    conn_uuid = uuid.UUID(connection_id)
    tenant_uuid = uuid.UUID(tenant_id)

    engine = None
    redis_client = None
    try:
        engine = create_async_engine(settings.database_url, echo=False)
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    except Exception as setup_exc:
        log.error("discovery.setup.failed", error=str(setup_exc))
        raise

    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _set_progress(stage: str, pct: int, detail: str = "") -> None:
        await redis_client.setex(
            _progress_key(job_id),
            3600,
            json.dumps({"stage": stage, "pct": pct, "detail": detail,
                        "updated_at": datetime.now(UTC).isoformat()}),
        )

    try:
        await _set_progress("starting", 0)

        async with SessionLocal() as db:
            # Load connection
            result = await db.execute(
                select(Connection).where(
                    Connection.id == conn_uuid,
                    Connection.tenant_id == tenant_uuid,
                    Connection.is_active.is_(True),
                )
            )
            connection = result.scalar_one_or_none()
            if not connection:
                raise ValueError(f"Connection {connection_id} not found or inactive")

            await _set_progress("connecting", 10, f"Connecting to {connection.db_type}")

            # Decrypt credentials
            vault_path = connection.vault_credential_path
            if not vault_path.startswith("local:"):
                raise ValueError("Unsupported vault path format")
            cred_json = decrypt(vault_path[len("local:"):])
            creds = json.loads(cred_json)

            # Open raw source-DB connection in threadpool (SchemaCrawler needs sync cursor)
            import asyncio
            raw_pw = decrypt(creds["encrypted_password"])

            def _open_conn():
                if connection.db_type == "hana":
                    try:
                        import hdbcli.dbapi as hdbapi  # type: ignore[import-untyped]
                    except ImportError:
                        raise RuntimeError("hdbcli not installed")
                    return hdbapi.connect(
                        address=connection.host,
                        port=connection.port,
                        user=creds["username"],
                        password=raw_pw,
                        encrypt=True,
                        sslValidateCertificate=True,
                    )
                elif connection.db_type == "mssql":
                    try:
                        import pyodbc  # type: ignore[import-untyped]
                    except ImportError:
                        raise RuntimeError("pyodbc not installed")
                    from app.services.connections.connector import build_mssql_conn_str
                    conn_str = build_mssql_conn_str(
                        host=connection.host,
                        port=connection.port,
                        database_name=connection.database_name,
                        username=creds["username"],
                        password=raw_pw,
                        is_tls=connection.is_tls,
                        timeout=30,
                    )
                    return pyodbc.connect(conn_str)
                else:
                    raise ValueError(f"Unsupported db_type: {connection.db_type}")

            src_conn = await asyncio.get_event_loop().run_in_executor(None, _open_conn)

            try:
                await _set_progress("crawling", 20, "Crawling schema metadata")

                crawler = SchemaCrawler(
                    db=db,
                    src_conn=src_conn,
                    db_type=connection.db_type,
                    tenant_id=tenant_uuid,
                    connection_id=conn_uuid,
                )

                if mode == "full":
                    counts = await crawler.run_full()
                else:
                    counts = await crawler.run_incremental()

                await _set_progress("done", 100, json.dumps(counts))

                # Update connection health
                connection.last_health_check_at = datetime.now(UTC).isoformat()
                connection.last_health_status = "ok"

                # Audit log
                audit = AuditService(db)
                await audit.log(
                    event_type=AuditEvent.DISCOVERY_COMPLETED,
                    tenant_id=tenant_uuid,
                    resource_type="connection",
                    resource_id=str(conn_uuid),
                    metadata={"mode": mode, "counts": counts, "triggered_by": triggered_by},
                )
                await db.commit()

                log.info("discovery.complete", mode=mode, job_id=job_id, counts=counts)

                # Kick off the downstream intelligence pipeline (semantic →
                # KG → tools → embeddings) so chat is usable without any
                # manual admin steps. Incremental crawls skip this; their
                # diffs are handled by targeted refresh tasks.
                if mode == "full":
                    build_post_discovery_pipeline(
                        connection_id=str(conn_uuid),
                        tenant_id=str(tenant_uuid),
                        db_type=connection.db_type,
                    ).delay()
                    log.info("discovery.pipeline_queued", connection_id=connection_id)

                return {"status": "success", "mode": mode, "counts": counts}

            finally:
                def _close():
                    try:
                        src_conn.close()
                    except Exception:
                        pass
                await asyncio.get_event_loop().run_in_executor(None, _close)

    except Exception as exc:
        await _set_progress("error", 0, str(exc))
        log.error("discovery.failed", mode=mode, job_id=job_id, error=str(exc))

        # Mark connection unhealthy
        try:
            engine2 = create_async_engine(settings.database_url, echo=False)
            async with async_sessionmaker(engine2, class_=AsyncSession,
                                          expire_on_commit=False)() as db2:
                from sqlalchemy import select
                r2 = await db2.execute(
                    select(Connection).where(Connection.id == conn_uuid)
                )
                conn2 = r2.scalar_one_or_none()
                if conn2:
                    conn2.last_health_check_at = datetime.now(UTC).isoformat()
                    conn2.last_health_status = "error"
                    await db2.commit()
        except Exception:
            pass

        raise task.retry(exc=exc)

    finally:
        if redis_client:
            await redis_client.aclose()
        if engine:
            await engine.dispose()
