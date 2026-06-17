"""
Tool Catalogue REST API — CRUD, custom builder, and ranking for parameterised SQL tools.

Spec: TG-005, TG-006, TG-007, TG-008, TR-001, TR-002
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequirePlatformAdmin, RequirePowerUserOrAbove, get_current_tenant
from app.core.database import get_db
from app.models.tool import Tool
from app.schemas.tools import (
    ToolCreate,
    ToolPackApplyResponse,
    ToolPatch,
    ToolResponse,
)
from app.worker.tasks.tools import (
    generate_kpi_tools,
    generate_tools_for_connection,
)

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get(
    "",
    response_model=list[ToolResponse],
    dependencies=[RequirePowerUserOrAbove],
)
async def list_tools(
    tenant: Annotated[dict, Depends(get_current_tenant)],
    domain: str | None = None,
    category: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List tools for the tenant with optional filters."""
    q = select(Tool).where(
        Tool.tenant_id == tenant["id"],
    )
    if domain:
        q = q.where(Tool.domain == domain)
    if category:
        q = q.where(Tool.category == category)
    if status_filter:
        q = q.where(Tool.status == status_filter)
    else:
        q = q.where(Tool.status == "active")
    if search:
        q = q.where(
            Tool.name.ilike(f"%{search}%") | Tool.description.ilike(f"%{search}%")
        )
    q = q.order_by(Tool.domain, Tool.category, Tool.name).offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.get(
    "/{tool_id}",
    response_model=ToolResponse,
    dependencies=[RequirePowerUserOrAbove],
)
async def get_tool(
    tool_id: uuid.UUID,
    tenant: Annotated[dict, Depends(get_current_tenant)],
    db: AsyncSession = Depends(get_db),
):
    """Get tool detail by ID."""
    result = await db.execute(
        select(Tool).where(
            Tool.id == tool_id,
            Tool.tenant_id == tenant["id"],
        )
    )
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool


@router.post(
    "",
    response_model=ToolResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[RequirePlatformAdmin],
)
async def create_tool(
    body: ToolCreate,
    tenant: Annotated[dict, Depends(get_current_tenant)],
    db: AsyncSession = Depends(get_db),
):
    """Create a custom tool (human-authored)."""
    # Check name uniqueness
    existing = await db.execute(
        select(Tool).where(
            Tool.tenant_id == tenant["id"],
            Tool.name == body.name,
            Tool.status == "active",
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409, detail=f"Active tool '{body.name}' already exists"
        )

    tool = Tool(
        tenant_id=tenant["id"],
        name=body.name,
        description=body.description,
        category=body.category,
        domain=body.domain,
        status="active",
        version=1,
        is_system=False,
        is_human_override=True,
        pack_source="human",
        sql_template=body.sql_template,
        input_schema=body.input_schema,
        output_schema=body.output_schema,
        permissions=body.permissions or {"required_domains": [body.domain]},
    )
    db.add(tool)
    await db.commit()
    await db.refresh(tool)
    return tool


@router.patch(
    "/{tool_id}",
    response_model=ToolResponse,
    dependencies=[RequirePlatformAdmin],
)
async def patch_tool(
    tool_id: uuid.UUID,
    body: ToolPatch,
    tenant: Annotated[dict, Depends(get_current_tenant)],
    db: AsyncSession = Depends(get_db),
):
    """Update tool description, SQL template, or status. Bumps version on SQL change."""
    result = await db.execute(
        select(Tool).where(
            Tool.id == tool_id,
            Tool.tenant_id == tenant["id"],
        )
    )
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    if body.description is not None:
        tool.description = body.description
    if body.status is not None:
        tool.status = body.status
    if body.input_schema is not None:
        tool.input_schema = body.input_schema
    if body.output_schema is not None:
        tool.output_schema = body.output_schema
    if body.sql_template is not None and body.sql_template != tool.sql_template:
        # Deprecate current version and create new
        tool.status = "deprecated"
        new_tool = Tool(
            tenant_id=tool.tenant_id,
            name=tool.name,
            description=body.description or tool.description,
            category=tool.category,
            domain=tool.domain,
            status="active",
            version=tool.version + 1,
            is_system=tool.is_system,
            is_human_override=True,
            pack_source=tool.pack_source,
            sql_template=body.sql_template,
            input_schema=body.input_schema or tool.input_schema,
            output_schema=body.output_schema or tool.output_schema,
            permissions=tool.permissions,
        )
        db.add(new_tool)
        await db.commit()
        await db.refresh(new_tool)
        return new_tool

    await db.commit()
    await db.refresh(tool)
    return tool


@router.delete(
    "/{tool_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[RequirePlatformAdmin],
)
async def delete_tool(
    tool_id: uuid.UUID,
    tenant: Annotated[dict, Depends(get_current_tenant)],
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete (deprecate) a tool."""
    result = await db.execute(
        select(Tool).where(
            Tool.id == tool_id,
            Tool.tenant_id == tenant["id"],
        )
    )
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    tool.status = "deprecated"
    await db.commit()


# ── Async generation actions ──────────────────────────────────────────────────

@router.post(
    "/actions/generate-for-connection",
    response_model=ToolPackApplyResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[RequirePlatformAdmin],
)
async def action_generate_connection(
    connection_id: uuid.UUID,
    tenant: Annotated[dict, Depends(get_current_tenant)],
):
    """Auto-generate tools for all entities in a connection."""
    task = generate_tools_for_connection.delay(
        connection_id=str(connection_id),
        tenant_id=str(tenant["id"]),
    )
    return ToolPackApplyResponse(job_id=task.id, status="queued", pack_source="ai_generated")


@router.post(
    "/actions/generate-kpi-tools",
    response_model=ToolPackApplyResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[RequirePlatformAdmin],
)
async def action_generate_kpi_tools(
    tenant: Annotated[dict, Depends(get_current_tenant)],
):
    """Generate one tool per active KPI definition."""
    task = generate_kpi_tools.delay(tenant_id=str(tenant["id"]))
    return ToolPackApplyResponse(job_id=task.id, status="queued", pack_source="kpi")


# ── Custom Tool Builder ───────────────────────────────────────────────────────

class CustomBuildRequest(BaseModel):
    description: str
    context_tables: list[str] | None = None


class CustomBuildResponse(BaseModel):
    success: bool
    tool: "ToolResponse | None" = None
    error: str | None = None


@router.post(
    "/custom-build",
    response_model=CustomBuildResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[RequirePlatformAdmin],
)
async def custom_build_tool(
    body: CustomBuildRequest,
    tenant: Annotated[dict, Depends(get_current_tenant)],
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a custom SQL tool from a plain-English description using Claude.
    The generated SQL is validated (SELECT-only) before storage.
    """
    from app.services.tools.custom_builder import CustomToolBuilder
    from app.schemas.tools import ToolResponse

    builder = CustomToolBuilder(db, tenant["id"])
    result = await builder.build_from_description(
        description=body.description,
        created_by=tenant["user_id"],
        context_tables=body.context_tables,
    )
    await db.commit()

    if result.success and result.tool:
        await db.refresh(result.tool)
        return CustomBuildResponse(
            success=True,
            tool=ToolResponse.model_validate(result.tool),
        )
    return CustomBuildResponse(success=False, error=result.error)


# ── Tool Ranking ──────────────────────────────────────────────────────────────

class RankedToolResponse(BaseModel):
    tool_id: uuid.UUID
    tool_name: str
    description: str | None
    domain: str
    category: str
    final_score: float
    semantic_similarity: float
    success_rate: float
    feedback_weight: float


@router.get(
    "/rank",
    response_model=list[RankedToolResponse],
    dependencies=[RequirePowerUserOrAbove],
)
async def rank_tools(
    q: str = Query(..., min_length=2, description="Natural-language query"),
    domain: str | None = None,
    top_k: int = Query(5, ge=1, le=20),
    tenant: Annotated[dict, Depends(get_current_tenant)] = None,
    db: AsyncSession = Depends(get_db),
):
    """Return ranked tool candidates for a natural-language query."""
    from app.services.tools.ranker import ToolRanker
    ranker = ToolRanker(db, tenant["id"])
    results = await ranker.rank(q, detected_domain=domain, top_k=top_k)
    return [
        RankedToolResponse(
            tool_id=r.tool_id,
            tool_name=r.tool_name,
            description=r.description,
            domain=r.domain,
            category=r.category,
            final_score=r.final_score,
            semantic_similarity=r.semantic_similarity,
            success_rate=r.success_rate,
            feedback_weight=r.feedback_weight,
        )
        for r in results
    ]
