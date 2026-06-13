"""
Dashboards REST API.

Spec: VE-012, DB-001–DB-006
  - DB-001: POST /dashboards — create a named dashboard
  - DB-002: GET /dashboards — list user's dashboards
  - DB-003: GET /dashboards/{id} — single dashboard with widgets
  - DB-004: PATCH /dashboards/{id} — rename / toggle share / save layout
  - DB-005: DELETE /dashboards/{id} — delete dashboard + widgets
  - DB-006: POST /dashboards/{id}/widgets — pin a turn as a widget
  - DB-007: PATCH /dashboards/{id}/widgets/{wid} — reposition/retitle widget
  - DB-008: DELETE /dashboards/{id}/widgets/{wid} — remove widget

RLS: all queries filter by tenant_id.
Share tokens: generated on demand when is_shared is set to True.
"""

from __future__ import annotations

import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.dashboard import Dashboard, DashboardWidget
from app.schemas.dashboard import (
    DashboardCreate,
    DashboardPatch,
    DashboardResponse,
    WidgetCreate,
    WidgetPatch,
    WidgetResponse,
)

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_dashboard_or_404(
    db: AsyncSession,
    dashboard_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> Dashboard:
    result = await db.execute(
        select(Dashboard).where(
            Dashboard.id == dashboard_id,
            Dashboard.tenant_id == tenant_id,
        )
    )
    obj = result.scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return obj


# ── Dashboard CRUD ────────────────────────────────────────────────────────────

@router.post("", response_model=DashboardResponse, status_code=status.HTTP_201_CREATED)
async def create_dashboard(
    body: DashboardCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
):
    dash = Dashboard(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        name=body.name,
        is_shared=body.is_shared,
        share_token=secrets.token_urlsafe(24) if body.is_shared else None,
    )
    db.add(dash)
    await db.commit()
    await db.refresh(dash)
    return dash


@router.get("", response_model=list[DashboardResponse])
async def list_dashboards(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(Dashboard).where(
            Dashboard.tenant_id == current_user.tenant_id,
            Dashboard.user_id == current_user.id,
        ).order_by(Dashboard.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{dashboard_id}", response_model=DashboardResponse)
async def get_dashboard(
    dashboard_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
):
    return await _get_dashboard_or_404(db, dashboard_id, current_user.tenant_id)


@router.patch("/{dashboard_id}", response_model=DashboardResponse)
async def patch_dashboard(
    dashboard_id: uuid.UUID,
    body: DashboardPatch,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
):
    dash = await _get_dashboard_or_404(db, dashboard_id, current_user.tenant_id)
    if body.name is not None:
        dash.name = body.name
    if body.layout is not None:
        dash.layout = body.layout
    if body.is_shared is not None:
        dash.is_shared = body.is_shared
        if body.is_shared and not dash.share_token:
            dash.share_token = secrets.token_urlsafe(24)
        elif not body.is_shared:
            dash.share_token = None
    await db.commit()
    await db.refresh(dash)
    return dash


@router.delete("/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dashboard(
    dashboard_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
):
    dash = await _get_dashboard_or_404(db, dashboard_id, current_user.tenant_id)
    await db.delete(dash)
    await db.commit()


# ── Widget CRUD ───────────────────────────────────────────────────────────────

@router.get("/{dashboard_id}/widgets", response_model=list[WidgetResponse])
async def list_widgets(
    dashboard_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
):
    await _get_dashboard_or_404(db, dashboard_id, current_user.tenant_id)
    result = await db.execute(
        select(DashboardWidget)
        .where(DashboardWidget.dashboard_id == dashboard_id)
        .order_by(DashboardWidget.position_y, DashboardWidget.position_x)
    )
    return result.scalars().all()


@router.post(
    "/{dashboard_id}/widgets",
    response_model=WidgetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_widget(
    dashboard_id: uuid.UUID,
    body: WidgetCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
):
    await _get_dashboard_or_404(db, dashboard_id, current_user.tenant_id)
    widget = DashboardWidget(
        dashboard_id=dashboard_id,
        conversation_turn_id=body.conversation_turn_id,
        title=body.title,
        widget_type=body.widget_type,
        position_x=body.position_x,
        position_y=body.position_y,
        width=body.width,
        height=body.height,
    )
    db.add(widget)
    await db.commit()
    await db.refresh(widget)
    return widget


@router.patch("/{dashboard_id}/widgets/{widget_id}", response_model=WidgetResponse)
async def patch_widget(
    dashboard_id: uuid.UUID,
    widget_id: uuid.UUID,
    body: WidgetPatch,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
):
    await _get_dashboard_or_404(db, dashboard_id, current_user.tenant_id)
    result = await db.execute(
        select(DashboardWidget).where(
            DashboardWidget.id == widget_id,
            DashboardWidget.dashboard_id == dashboard_id,
        )
    )
    widget = result.scalar_one_or_none()
    if widget is None:
        raise HTTPException(status_code=404, detail="Widget not found")

    for field, val in body.model_dump(exclude_none=True).items():
        setattr(widget, field, val)
    await db.commit()
    await db.refresh(widget)
    return widget


@router.delete(
    "/{dashboard_id}/widgets/{widget_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_widget(
    dashboard_id: uuid.UUID,
    widget_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
):
    await _get_dashboard_or_404(db, dashboard_id, current_user.tenant_id)
    result = await db.execute(
        select(DashboardWidget).where(
            DashboardWidget.id == widget_id,
            DashboardWidget.dashboard_id == dashboard_id,
        )
    )
    widget = result.scalar_one_or_none()
    if widget is None:
        raise HTTPException(status_code=404, detail="Widget not found")
    await db.delete(widget)
    await db.commit()
