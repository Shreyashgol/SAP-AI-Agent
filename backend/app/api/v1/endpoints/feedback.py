"""
Feedback REST API.

Endpoints:
  POST   /feedback              — submit thumbs up/down (FL-001)
  GET    /feedback              — list tenant feedback (admin)
  POST   /feedback/corrections  — submit answer correction (FL-002)
  GET    /feedback/corrections  — list corrections (admin)
  PATCH  /feedback/corrections/{id} — approve/reject correction (admin)

After each feedback submission, triggers async weight recalculation.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequirePlatformAdmin, get_current_user, get_db, get_current_tenant
from app.models.feedback import FeedbackCorrection, UserFeedback
from app.schemas.feedback import (
    CorrectionCreate,
    CorrectionResponse,
    FeedbackCreate,
    FeedbackResponse,
)

router = APIRouter(prefix="/feedback", tags=["feedback"])


# ── Submit feedback ───────────────────────────────────────────────────────────

@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    body: FeedbackCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
    tenant=Depends(get_current_tenant),
):
    fb = UserFeedback(
        tenant_id=tenant["id"],
        user_id=current_user.id,
        conversation_turn_id=body.conversation_turn_id,
        tool_id=body.tool_id,
        rating=body.rating,
    )
    db.add(fb)
    await db.commit()
    await db.refresh(fb)

    # Trigger async weight recalculation
    try:
        from app.worker.tasks.embedding import recalculate_weights
        recalculate_weights.delay(tenant_id=str(tenant["id"]))
    except Exception:
        pass  # Non-fatal — weights update nightly anyway

    return fb


# ── List feedback (admin) ─────────────────────────────────────────────────────

@router.get("", response_model=list[FeedbackResponse], dependencies=[RequirePlatformAdmin])
async def list_feedback(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant=Depends(get_current_tenant),
    limit: int = 50,
    offset: int = 0,
):
    result = await db.execute(
        select(UserFeedback)
        .where(UserFeedback.tenant_id == tenant["id"])
        .order_by(UserFeedback.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


# ── Submit correction ─────────────────────────────────────────────────────────

@router.post(
    "/corrections",
    response_model=CorrectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_correction(
    body: CorrectionCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
    tenant=Depends(get_current_tenant),
):
    correction = FeedbackCorrection(
        tenant_id=tenant["id"],
        user_id=current_user.id,
        conversation_turn_id=body.conversation_turn_id,
        correction_text=body.correction_text,
        admin_status="pending",
    )
    db.add(correction)
    await db.commit()
    await db.refresh(correction)
    return correction


# ── List corrections (admin) ──────────────────────────────────────────────────

@router.get(
    "/corrections",
    response_model=list[CorrectionResponse],
    dependencies=[RequirePlatformAdmin],
)
async def list_corrections(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant=Depends(get_current_tenant),
    admin_status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    query = select(FeedbackCorrection).where(
        FeedbackCorrection.tenant_id == tenant["id"]
    )
    if admin_status:
        query = query.where(FeedbackCorrection.admin_status == admin_status)
    query = query.order_by(FeedbackCorrection.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


# ── Review correction (admin) ─────────────────────────────────────────────────

@router.patch(
    "/corrections/{correction_id}",
    response_model=CorrectionResponse,
    dependencies=[RequirePlatformAdmin],
)
async def review_correction(
    correction_id: uuid.UUID,
    admin_status: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
    tenant=Depends(get_current_tenant),
):
    if admin_status not in ("approved", "rejected"):
        raise HTTPException(status_code=422, detail="admin_status must be 'approved' or 'rejected'")

    result = await db.execute(
        select(FeedbackCorrection).where(
            FeedbackCorrection.id == correction_id,
            FeedbackCorrection.tenant_id == tenant["id"],
        )
    )
    correction = result.scalar_one_or_none()
    if not correction:
        raise HTTPException(status_code=404, detail="Correction not found")

    correction.admin_status = admin_status
    correction.reviewed_by = current_user.id
    await db.commit()
    await db.refresh(correction)
    return correction
