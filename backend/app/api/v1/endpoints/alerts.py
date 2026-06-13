"""
Alerts REST API.

Spec: PI-002, PI-004, PI-010
  - GET  /alert-rules          — list rules for tenant
  - POST /alert-rules          — create rule
  - PATCH /alert-rules/{id}    — update (name / threshold / active)
  - DELETE /alert-rules/{id}   — delete rule (cascades to alerts)
  - GET  /alerts               — list triggered alerts (filterable by status/severity)
  - POST /alerts/{id}/action   — acknowledge / snooze / escalate

All queries are RLS-guarded via tenant_id filter.
Alerts table is append-only (no UPDATE/DELETE) — action updates status only.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.analytics import AlertRule, Alert
from app.schemas.alert import (
    AlertAcknowledge,
    AlertResponse,
    AlertRuleCreate,
    AlertRulePatch,
    AlertRuleResponse,
)

router = APIRouter(tags=["alerts"])


# ── Alert rules ───────────────────────────────────────────────────────────────

@router.get("/alert-rules", response_model=list[AlertRuleResponse])
async def list_alert_rules(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
    active_only: bool = Query(default=False),
):
    q = select(AlertRule).where(AlertRule.tenant_id == current_user.tenant_id)
    if active_only:
        q = q.where(AlertRule.is_active == True)  # noqa: E712
    q = q.order_by(AlertRule.created_at.desc())
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/alert-rules", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    body: AlertRuleCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
):
    rule = AlertRule(
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
        name=body.name,
        rule_type=body.rule_type,
        kpi_id=body.kpi_id,
        operator=body.operator,
        threshold_value=body.threshold_value,
        severity=body.severity,
        assigned_role_ids=[str(r) for r in body.assigned_role_ids],
        monitoring_schedule=body.monitoring_schedule,
        is_active=True,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.patch("/alert-rules/{rule_id}", response_model=AlertRuleResponse)
async def patch_alert_rule(
    rule_id: uuid.UUID,
    body: AlertRulePatch,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(AlertRule).where(
            AlertRule.id == rule_id,
            AlertRule.tenant_id == current_user.tenant_id,
        )
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(rule, field, val)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/alert-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_rule(
    rule_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(AlertRule).where(
            AlertRule.id == rule_id,
            AlertRule.tenant_id == current_user.tenant_id,
        )
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    await db.delete(rule)
    await db.commit()


# ── Triggered alerts ──────────────────────────────────────────────────────────

@router.get("/alerts", response_model=list[AlertResponse])
async def list_alerts(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
    status_filter: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
):
    q = select(Alert).where(Alert.tenant_id == current_user.tenant_id)
    if status_filter:
        q = q.where(Alert.status == status_filter)
    if severity:
        q = q.where(Alert.severity == severity)
    q = q.order_by(Alert.created_at.desc()).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/alerts/{alert_id}/action", response_model=AlertResponse)
async def alert_action(
    alert_id: uuid.UUID,
    body: AlertAcknowledge,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
):
    """Acknowledge, snooze, or escalate an alert."""
    result = await db.execute(
        select(Alert).where(
            Alert.id == alert_id,
            Alert.tenant_id == current_user.tenant_id,
        )
    )
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.status = body.status
    if body.status == "acknowledged":
        alert.acknowledged_by = current_user.id
    if body.status == "snoozed" and body.snoozed_until:
        alert.snoozed_until = body.snoozed_until
    await db.commit()
    await db.refresh(alert)
    return alert
