"""
Report Schedules REST API.

Spec: RD-001, RD-002, RD-010
  - POST   /report-schedules          — create schedule
  - GET    /report-schedules          — list schedules
  - GET    /report-schedules/{id}     — single schedule
  - PATCH  /report-schedules/{id}     — update (name / questions / cron / active)
  - DELETE /report-schedules/{id}     — delete (cascades executions)
  - POST   /report-schedules/{id}/run — trigger immediate execution
  - GET    /report-schedules/{id}/executions — list past executions

Scheduled execution is triggered by RedBeat via Celery task run_report_schedule.
Manual /run enqueues the same task immediately.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.report import ReportSchedule, ReportExecution
from app.schemas.report import (
    ReportExecutionResponse,
    ReportScheduleCreate,
    ReportSchedulePatch,
    ReportScheduleResponse,
)

router = APIRouter(prefix="/report-schedules", tags=["reports"])


async def _get_schedule_or_404(
    db: AsyncSession, schedule_id: uuid.UUID, tenant_id: uuid.UUID
) -> ReportSchedule:
    result = await db.execute(
        select(ReportSchedule).where(
            ReportSchedule.id == schedule_id,
            ReportSchedule.tenant_id == tenant_id,
        )
    )
    obj = result.scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=404, detail="Report schedule not found")
    return obj


@router.post("", response_model=ReportScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    body: ReportScheduleCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
):
    sched = ReportSchedule(
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
        name=body.name,
        questions=body.questions,
        cron_expression=body.cron_expression,
        delivery_channels=body.delivery_channels,
        subscriber_ids=[str(s) for s in body.subscriber_ids],
        is_active=True,
    )
    db.add(sched)
    await db.commit()
    await db.refresh(sched)
    return sched


@router.get("", response_model=list[ReportScheduleResponse])
async def list_schedules(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(ReportSchedule)
        .where(ReportSchedule.tenant_id == current_user.tenant_id)
        .order_by(ReportSchedule.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{schedule_id}", response_model=ReportScheduleResponse)
async def get_schedule(
    schedule_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
):
    return await _get_schedule_or_404(db, schedule_id, current_user.tenant_id)


@router.patch("/{schedule_id}", response_model=ReportScheduleResponse)
async def patch_schedule(
    schedule_id: uuid.UUID,
    body: ReportSchedulePatch,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
):
    sched = await _get_schedule_or_404(db, schedule_id, current_user.tenant_id)
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(sched, field, val)
    await db.commit()
    await db.refresh(sched)
    return sched


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    schedule_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
):
    sched = await _get_schedule_or_404(db, schedule_id, current_user.tenant_id)
    await db.delete(sched)
    await db.commit()


@router.post("/{schedule_id}/run", response_model=ReportExecutionResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_run(
    schedule_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
):
    """Enqueue an immediate execution of the report schedule."""
    sched = await _get_schedule_or_404(db, schedule_id, current_user.tenant_id)

    # Create execution record
    execution = ReportExecution(
        tenant_id=current_user.tenant_id,
        schedule_id=sched.id,
        status="pending",
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)

    # Enqueue Celery task
    try:
        from app.worker.tasks.report import run_report_schedule
        run_report_schedule.delay(
            str(sched.id),
            str(execution.id),
            str(current_user.tenant_id),
        )
    except Exception:
        pass  # Task enqueue failure does not fail the API — execution is in "pending" state

    return execution


@router.get("/{schedule_id}/executions", response_model=list[ReportExecutionResponse])
async def list_executions(
    schedule_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
):
    await _get_schedule_or_404(db, schedule_id, current_user.tenant_id)
    result = await db.execute(
        select(ReportExecution)
        .where(
            ReportExecution.schedule_id == schedule_id,
            ReportExecution.tenant_id == current_user.tenant_id,
        )
        .order_by(ReportExecution.created_at.desc())
        .limit(50)
    )
    return result.scalars().all()
