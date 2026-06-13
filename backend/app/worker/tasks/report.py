"""
Report execution Celery task.

Spec: RD-010
  run_report_schedule(schedule_id, execution_id, tenant_id)
    1. Load schedule + connection_id (from tenant default connection)
    2. For each NL question in schedule.questions:
       - Run through the LangGraph agent (run_question)
       - Collect answer_text, sql_query, answer_data
    3. Serialize results as JSON to settings.report_storage_path/{execution_id}.json
    4. Mark execution as completed (or failed with error_message)
    5. Delivery stub: logs delivery channels; real delivery (email/webhook)
       is a Phase 6 / v1.1 feature

The task is idempotent — if re-queued with the same execution_id, the
existing completed/failed record is left unchanged.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.worker.celery_app import celery_app
from app.core.logging import get_logger

log = get_logger("task.report")


@celery_app.task(
    name="tasks.run_report_schedule",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    acks_late=True,
)
def run_report_schedule(
    self,
    schedule_id: str,
    execution_id: str,
    tenant_id: str,
) -> dict:
    """Execute all questions in a report schedule and store results."""
    return asyncio.get_event_loop().run_until_complete(
        _async_run(self, schedule_id, execution_id, tenant_id)
    )


async def _async_run(task, schedule_id: str, execution_id: str, tenant_id: str) -> dict:
    from app.worker.db import AsyncSessionLocal
    from app.models.report import ReportSchedule, ReportExecution
    from sqlalchemy import select

    exec_id = uuid.UUID(execution_id)
    sched_id = uuid.UUID(schedule_id)
    t_id = uuid.UUID(tenant_id)

    start_ms = int(time.time() * 1000)

    async with AsyncSessionLocal() as db:
        # Load execution record
        res = await db.execute(
            select(ReportExecution).where(ReportExecution.id == exec_id)
        )
        execution = res.scalar_one_or_none()
        if execution is None:
            log.error("report.execution_not_found", execution_id=execution_id)
            return {"status": "not_found"}

        # Idempotency guard
        if execution.status in ("completed", "failed"):
            log.info("report.already_done", execution_id=execution_id, status=execution.status)
            return {"status": execution.status}

        # Mark running
        execution.status = "running"
        await db.commit()

        # Load schedule
        res = await db.execute(
            select(ReportSchedule).where(
                ReportSchedule.id == sched_id,
                ReportSchedule.tenant_id == t_id,
            )
        )
        schedule = res.scalar_one_or_none()
        if schedule is None:
            execution.status = "failed"
            execution.error_message = "Schedule not found"
            await db.commit()
            return {"status": "failed"}

    # Run each NL question through the agent
    from app.agents.supervisor import run_question
    from app.core.settings import get_settings

    settings = get_settings()
    sections = []
    errors: list[str] = []

    for question in schedule.questions:
        try:
            state = {
                "messages": [],
                "question": question,
                "tenant_id": t_id,
                "user_id": uuid.UUID("00000000-0000-0000-0000-000000000001"),  # system user
                "conversation_id": exec_id,
                "turn_id": uuid.uuid4(),
                "connection_id": None,
                "intent": None,
                "detected_domain": None,
                "enriched_question": None,
                "confidence": None,
                "candidate_tools": [],
                "selected_tool": None,
                "resolved_params": {},
                "join_path": None,
                "entity_ids": [],
                "sql_query": None,
                "query_result": None,
                "execution_time_ms": None,
                "answer_text": None,
                "answer_data": None,
                "chart_hint": None,
                "follow_up_questions": [],
                "lineage": None,
                "confidence_score": None,
                "error": None,
                "fallback_used": False,
                "agents_invoked": [],
                "needs_clarification": False,
                "missing_params": [],
                "clarification_question": None,
            }
            final = await run_question(state)
            sections.append({
                "question": question,
                "answer_text": final.get("answer_text"),
                "sql_query": final.get("sql_query"),
                "chart_hint": final.get("chart_hint"),
                "confidence_score": final.get("confidence_score"),
                "error": final.get("error"),
            })
        except Exception as exc:
            log.warning("report.question_failed", question=question[:60], exc=str(exc))
            errors.append(f"{question[:60]}: {exc}")
            sections.append({"question": question, "error": str(exc)})

    # Persist output JSON
    report_payload = {
        "schedule_id": schedule_id,
        "execution_id": execution_id,
        "tenant_id": tenant_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sections": sections,
    }
    storage_path = str(
        Path(settings.document_storage_path).parent / "reports" / f"{execution_id}.json"
    )
    try:
        Path(storage_path).parent.mkdir(parents=True, exist_ok=True)
        Path(storage_path).write_text(json.dumps(report_payload, default=str), encoding="utf-8")
    except Exception as exc:
        log.warning("report.storage_fail", exc=str(exc))
        storage_path = None

    # Delivery stub — log channels, real delivery is Phase 6
    channels = schedule.delivery_channels or {}
    log.info(
        "report.delivery_stub",
        execution_id=execution_id,
        channels=list(channels.keys()),
        sections=len(sections),
    )

    elapsed = int(time.time() * 1000) - start_ms

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        res = await db.execute(
            select(ReportExecution).where(ReportExecution.id == exec_id)
        )
        execution = res.scalar_one_or_none()
        if execution:
            execution.status = "failed" if (errors and len(errors) == len(sections)) else "completed"
            execution.storage_path = storage_path
            execution.execution_time_ms = elapsed
            execution.delivered_at = datetime.now(timezone.utc).isoformat()
            if errors:
                execution.error_message = "; ".join(errors[:3])
            await db.commit()

    log.info("report.done", execution_id=execution_id, elapsed_ms=elapsed, sections=len(sections))
    return {"status": "completed", "sections": len(sections)}
