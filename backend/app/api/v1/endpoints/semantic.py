"""
Semantic layer REST API.

Entities:
  GET    /semantic/entities              — list with connection/domain filter
  GET    /semantic/entities/{id}         — entity detail + attributes
  PATCH  /semantic/entities/{id}         — human override (name/domain/description)

Attributes:
  PATCH  /semantic/attributes/{id}       — override display_name/semantic_type

KPIs:
  GET    /semantic/kpis                  — list with domain filter
  POST   /semantic/kpis                  — create custom KPI
  PATCH  /semantic/kpis/{id}             — update KPI

Glossary:
  GET    /semantic/glossary              — list all terms
  POST   /semantic/glossary              — add term
  PATCH  /semantic/glossary/{id}         — update term
  DELETE /semantic/glossary/{id}         — remove term

Synonyms:
  GET    /semantic/synonyms              — list
  POST   /semantic/synonyms              — add
  DELETE /semantic/synonyms/{id}         — remove

Business Rules:
  GET    /semantic/entities/{id}/rules   — rules for entity
  POST   /semantic/entities/{id}/rules   — add rule
  PATCH  /semantic/rules/{id}            — update rule
  DELETE /semantic/rules/{id}            — remove rule

Pack / AI mapping:
  POST   /semantic/apply-pack            — trigger pack loader (Celery)
  POST   /semantic/ai-map                — trigger AI entity mapping
  POST   /semantic/seed-kpis             — seed system KPIs for tenant
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, RequirePlatformAdmin, RequirePowerUserOrAbove
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.semantic import (
    BusinessGlossary,
    BusinessRule,
    KpiDefinition,
    SemanticAttribute,
    SemanticEntity,
    SynonymMapping,
)
from app.schemas.base import APIResponse, PaginatedResponse
from app.schemas.semantic import (
    AIMapRequest,
    AIMapResponse,
    ApplyPackRequest,
    ApplyPackResponse,
    AttributePatch,
    AttributeResponse,
    BusinessRuleCreate,
    BusinessRulePatch,
    BusinessRuleResponse,
    EntityPatch,
    EntityResponse,
    GlossaryCreate,
    GlossaryPatch,
    GlossaryResponse,
    KPICreate,
    KPIPatch,
    KPIResponse,
    SynonymCreate,
    SynonymResponse,
)

router = APIRouter(prefix="/semantic", tags=["semantic"])


# ── Entities ───────────────────────────────────────────────────────────────────

@router.get("/entities", response_model=PaginatedResponse[EntityResponse],
            dependencies=[RequirePowerUserOrAbove])
async def list_entities(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    domain: str | None = Query(None),
    connection_id: uuid.UUID | None = Query(None),
    ai_only: bool = Query(False, description="Show only AI-generated (unreviewed) entities"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> PaginatedResponse[EntityResponse]:
    from app.models.metadata import MetadataTable

    q = select(SemanticEntity).where(SemanticEntity.tenant_id == current_user.tenant_id)
    if domain:
        q = q.where(SemanticEntity.domain == domain)
    if ai_only:
        q = q.where(
            SemanticEntity.is_ai_generated.is_(True),
            SemanticEntity.is_human_override.is_(False),
        )
    if connection_id:
        # Filter by connection via join to MetadataTable
        q = q.join(MetadataTable, MetadataTable.id == SemanticEntity.table_id).where(
            MetadataTable.connection_id == connection_id
        )

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await db.execute(
        q.order_by(SemanticEntity.entity_name)
         .offset((page - 1) * page_size)
         .limit(page_size)
    )).scalars().all()

    return PaginatedResponse(
        success=True,
        data=[_entity_response(e) for e in rows],
        total=total, page=page, page_size=page_size,
    )


@router.get("/entities/{entity_id}", response_model=APIResponse[dict],
            dependencies=[RequirePowerUserOrAbove])
async def get_entity(
    entity_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    entity = await _get_entity_or_404(entity_id, current_user.tenant_id, db)
    attrs = (await db.execute(
        select(SemanticAttribute).where(SemanticAttribute.entity_id == entity_id)
    )).scalars().all()
    rules = (await db.execute(
        select(BusinessRule).where(BusinessRule.entity_id == entity_id)
    )).scalars().all()

    return APIResponse(success=True, data={
        **_entity_response(entity).model_dump(),
        "attributes": [_attr_response(a).model_dump() for a in attrs],
        "rules": [_rule_response(r).model_dump() for r in rules],
    })


@router.patch("/entities/{entity_id}", response_model=APIResponse[EntityResponse],
              dependencies=[RequirePlatformAdmin])
async def patch_entity(
    entity_id: uuid.UUID,
    body: EntityPatch,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[EntityResponse]:
    entity = await _get_entity_or_404(entity_id, current_user.tenant_id, db)
    if body.entity_name is not None:
        entity.entity_name = body.entity_name
    if body.domain is not None:
        entity.domain = body.domain
    if body.description is not None:
        entity.description = body.description
    entity.is_human_override = True
    entity.semantic_version += 1
    await db.commit()
    await db.refresh(entity)
    return APIResponse(success=True, data=_entity_response(entity))


# ── Attributes ─────────────────────────────────────────────────────────────────

@router.patch("/attributes/{attr_id}", response_model=APIResponse[AttributeResponse],
              dependencies=[RequirePlatformAdmin])
async def patch_attribute(
    attr_id: uuid.UUID,
    body: AttributePatch,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[AttributeResponse]:
    result = await db.execute(
        select(SemanticAttribute).where(
            SemanticAttribute.id == attr_id,
            SemanticAttribute.tenant_id == current_user.tenant_id,
        )
    )
    attr = result.scalar_one_or_none()
    if not attr:
        raise NotFoundError("Attribute")
    if body.display_name is not None:
        attr.display_name = body.display_name
    if body.semantic_type is not None:
        attr.semantic_type = body.semantic_type
    if body.description is not None:
        attr.description = body.description
    attr.is_human_override = True
    await db.commit()
    await db.refresh(attr)
    return APIResponse(success=True, data=_attr_response(attr))


# ── KPIs ───────────────────────────────────────────────────────────────────────

@router.get("/kpis", response_model=PaginatedResponse[KPIResponse],
            dependencies=[RequirePowerUserOrAbove])
async def list_kpis(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    domain: str | None = Query(None),
    active_only: bool = Query(True),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[KPIResponse]:
    q = select(KpiDefinition).where(KpiDefinition.tenant_id == current_user.tenant_id)
    if domain:
        q = q.where(KpiDefinition.domain == domain)
    if active_only:
        q = q.where(KpiDefinition.is_active.is_(True))

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await db.execute(
        q.order_by(KpiDefinition.domain, KpiDefinition.display_name)
         .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()

    return PaginatedResponse(success=True, data=[_kpi_response(k) for k in rows],
                              total=total, page=page, page_size=page_size)


@router.post("/kpis", response_model=APIResponse[KPIResponse],
             dependencies=[RequirePlatformAdmin])
async def create_kpi(
    body: KPICreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[KPIResponse]:
    kpi = KpiDefinition(
        tenant_id=current_user.tenant_id,
        name=body.name,
        display_name=body.display_name,
        description=body.description,
        formula=body.formula,
        unit=body.unit,
        aggregation_method=body.aggregation_method,
        display_format=body.display_format,
        domain=body.domain,
        is_active=True,
        is_system=False,
    )
    db.add(kpi)
    await db.commit()
    await db.refresh(kpi)
    return APIResponse(success=True, data=_kpi_response(kpi))


@router.patch("/kpis/{kpi_id}", response_model=APIResponse[KPIResponse],
              dependencies=[RequirePlatformAdmin])
async def patch_kpi(
    kpi_id: uuid.UUID,
    body: KPIPatch,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[KPIResponse]:
    result = await db.execute(
        select(KpiDefinition).where(
            KpiDefinition.id == kpi_id,
            KpiDefinition.tenant_id == current_user.tenant_id,
        )
    )
    kpi = result.scalar_one_or_none()
    if not kpi:
        raise NotFoundError("KPI")
    if body.display_name is not None:
        kpi.display_name = body.display_name
    if body.description is not None:
        kpi.description = body.description
    if body.formula is not None:
        kpi.formula = body.formula
    if body.is_active is not None:
        kpi.is_active = body.is_active
    await db.commit()
    await db.refresh(kpi)
    return APIResponse(success=True, data=_kpi_response(kpi))


# ── Glossary ───────────────────────────────────────────────────────────────────

@router.get("/glossary", response_model=PaginatedResponse[GlossaryResponse],
            dependencies=[RequirePowerUserOrAbove])
async def list_glossary(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    domain: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[GlossaryResponse]:
    q = select(BusinessGlossary).where(BusinessGlossary.tenant_id == current_user.tenant_id)
    if domain:
        q = q.where(BusinessGlossary.domain == domain)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await db.execute(
        q.order_by(BusinessGlossary.term).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return PaginatedResponse(success=True, data=[_glossary_response(g) for g in rows],
                              total=total, page=page, page_size=page_size)


@router.post("/glossary", response_model=APIResponse[GlossaryResponse],
             dependencies=[RequirePlatformAdmin])
async def create_glossary_term(
    body: GlossaryCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[GlossaryResponse]:
    entry = BusinessGlossary(
        tenant_id=current_user.tenant_id,
        term=body.term,
        definition=body.definition,
        domain=body.domain,
        is_ai_generated=False,
        approved_by=current_user.id,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return APIResponse(success=True, data=_glossary_response(entry))


@router.patch("/glossary/{term_id}", response_model=APIResponse[GlossaryResponse],
              dependencies=[RequirePlatformAdmin])
async def patch_glossary_term(
    term_id: uuid.UUID,
    body: GlossaryPatch,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[GlossaryResponse]:
    result = await db.execute(
        select(BusinessGlossary).where(
            BusinessGlossary.id == term_id,
            BusinessGlossary.tenant_id == current_user.tenant_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise NotFoundError("Glossary term")
    if body.definition is not None:
        entry.definition = body.definition
    if body.domain is not None:
        entry.domain = body.domain
    entry.approved_by = current_user.id
    await db.commit()
    await db.refresh(entry)
    return APIResponse(success=True, data=_glossary_response(entry))


@router.delete("/glossary/{term_id}", response_model=APIResponse[None],
               dependencies=[RequirePlatformAdmin])
async def delete_glossary_term(
    term_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[None]:
    result = await db.execute(
        select(BusinessGlossary).where(
            BusinessGlossary.id == term_id,
            BusinessGlossary.tenant_id == current_user.tenant_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise NotFoundError("Glossary term")
    await db.delete(entry)
    await db.commit()
    return APIResponse(success=True, data=None)


# ── Synonyms ───────────────────────────────────────────────────────────────────

@router.get("/synonyms", response_model=PaginatedResponse[SynonymResponse],
            dependencies=[RequirePowerUserOrAbove])
async def list_synonyms(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    entity_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=1000),
) -> PaginatedResponse[SynonymResponse]:
    q = select(SynonymMapping).where(SynonymMapping.tenant_id == current_user.tenant_id)
    if entity_type:
        q = q.where(SynonymMapping.entity_type == entity_type)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await db.execute(
        q.order_by(SynonymMapping.synonym).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return PaginatedResponse(success=True,
                              data=[SynonymResponse(id=r.id, synonym=r.synonym,
                                    canonical_term=r.canonical_term,
                                    entity_type=r.entity_type) for r in rows],
                              total=total, page=page, page_size=page_size)


@router.post("/synonyms", response_model=APIResponse[SynonymResponse],
             dependencies=[RequirePlatformAdmin])
async def create_synonym(
    body: SynonymCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[SynonymResponse]:
    entry = SynonymMapping(
        tenant_id=current_user.tenant_id,
        synonym=body.synonym,
        canonical_term=body.canonical_term,
        entity_type=body.entity_type,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return APIResponse(success=True, data=SynonymResponse(id=entry.id, synonym=entry.synonym,
                        canonical_term=entry.canonical_term, entity_type=entry.entity_type))


@router.delete("/synonyms/{synonym_id}", response_model=APIResponse[None],
               dependencies=[RequirePlatformAdmin])
async def delete_synonym(
    synonym_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[None]:
    result = await db.execute(
        select(SynonymMapping).where(
            SynonymMapping.id == synonym_id,
            SynonymMapping.tenant_id == current_user.tenant_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise NotFoundError("Synonym")
    await db.delete(entry)
    await db.commit()
    return APIResponse(success=True, data=None)


# ── Business Rules ─────────────────────────────────────────────────────────────

@router.get("/entities/{entity_id}/rules", response_model=APIResponse[list[BusinessRuleResponse]],
            dependencies=[RequirePowerUserOrAbove])
async def list_entity_rules(
    entity_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[BusinessRuleResponse]]:
    await _get_entity_or_404(entity_id, current_user.tenant_id, db)
    rows = (await db.execute(
        select(BusinessRule).where(BusinessRule.entity_id == entity_id)
    )).scalars().all()
    return APIResponse(success=True, data=[_rule_response(r) for r in rows])


@router.post("/entities/{entity_id}/rules", response_model=APIResponse[BusinessRuleResponse],
             dependencies=[RequirePlatformAdmin])
async def create_entity_rule(
    entity_id: uuid.UUID,
    body: BusinessRuleCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[BusinessRuleResponse]:
    await _get_entity_or_404(entity_id, current_user.tenant_id, db)
    rule = BusinessRule(
        tenant_id=current_user.tenant_id,
        entity_id=entity_id,
        rule_name=body.rule_name,
        predicate_sql=body.predicate_sql,
        description=body.description,
        is_default=body.is_default,
        is_system=False,
        pack_source="human",
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return APIResponse(success=True, data=_rule_response(rule))


@router.patch("/rules/{rule_id}", response_model=APIResponse[BusinessRuleResponse],
              dependencies=[RequirePlatformAdmin])
async def patch_rule(
    rule_id: uuid.UUID,
    body: BusinessRulePatch,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[BusinessRuleResponse]:
    result = await db.execute(
        select(BusinessRule).where(
            BusinessRule.id == rule_id,
            BusinessRule.tenant_id == current_user.tenant_id,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise NotFoundError("Business rule")
    if body.predicate_sql is not None:
        rule.predicate_sql = body.predicate_sql
    if body.description is not None:
        rule.description = body.description
    if body.is_default is not None:
        rule.is_default = body.is_default
    rule.pack_source = "human"
    await db.commit()
    await db.refresh(rule)
    return APIResponse(success=True, data=_rule_response(rule))


@router.delete("/rules/{rule_id}", response_model=APIResponse[None],
               dependencies=[RequirePlatformAdmin])
async def delete_rule(
    rule_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[None]:
    result = await db.execute(
        select(BusinessRule).where(
            BusinessRule.id == rule_id,
            BusinessRule.tenant_id == current_user.tenant_id,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise NotFoundError("Business rule")
    await db.delete(rule)
    await db.commit()
    return APIResponse(success=True, data=None)


# ── Pack / AI mapping ──────────────────────────────────────────────────────────

@router.post("/apply-pack", response_model=APIResponse[ApplyPackResponse],
             dependencies=[RequirePlatformAdmin])
async def apply_pack(
    body: ApplyPackRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ApplyPackResponse]:
    from app.models.connection import Connection
    result = await db.execute(
        select(Connection).where(
            Connection.id == body.connection_id,
            Connection.tenant_id == current_user.tenant_id,
        )
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise NotFoundError("Connection")

    from app.worker.tasks.semantic import apply_entity_pack
    task = apply_entity_pack.delay(
        connection_id=str(body.connection_id),
        tenant_id=str(current_user.tenant_id),
        db_type=conn.db_type,
        schema_name=body.schema_name,
    )
    return APIResponse(success=True, data=ApplyPackResponse(
        job_id=task.id, status="queued"
    ))


@router.post("/ai-map", response_model=APIResponse[AIMapResponse],
             dependencies=[RequirePlatformAdmin])
async def trigger_ai_mapping(
    body: AIMapRequest,
    current_user: CurrentUser,
) -> APIResponse[AIMapResponse]:
    from app.worker.tasks.semantic import run_ai_mapping
    task = run_ai_mapping.delay(
        connection_id=str(body.connection_id),
        tenant_id=str(current_user.tenant_id),
        limit=body.limit,
    )
    return APIResponse(success=True, data=AIMapResponse(job_id=task.id, status="queued"))


@router.post("/seed-kpis", response_model=APIResponse[dict],
             dependencies=[RequirePlatformAdmin])
async def seed_kpis(current_user: CurrentUser) -> APIResponse[dict]:
    from app.worker.tasks.semantic import seed_tenant_kpis
    task = seed_tenant_kpis.delay(tenant_id=str(current_user.tenant_id))
    return APIResponse(success=True, data={"job_id": task.id, "status": "queued"})


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_entity_or_404(
    entity_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession
) -> SemanticEntity:
    result = await db.execute(
        select(SemanticEntity).where(
            SemanticEntity.id == entity_id,
            SemanticEntity.tenant_id == tenant_id,
        )
    )
    entity = result.scalar_one_or_none()
    if not entity:
        raise NotFoundError("Entity")
    return entity


def _entity_response(e: SemanticEntity) -> EntityResponse:
    return EntityResponse(
        id=e.id, table_id=e.table_id, entity_name=e.entity_name,
        domain=e.domain, description=e.description,
        is_ai_generated=e.is_ai_generated, is_human_override=e.is_human_override,
        confidence=e.confidence, pack_source=e.pack_source,
        semantic_version=e.semantic_version,
    )


def _attr_response(a: SemanticAttribute) -> AttributeResponse:
    return AttributeResponse(
        id=a.id, entity_id=a.entity_id, column_id=a.column_id,
        attribute_name=a.attribute_name, display_name=a.display_name,
        semantic_type=a.semantic_type, description=a.description,
        is_human_override=a.is_human_override, is_ai_generated=a.is_ai_generated,
    )


def _kpi_response(k: KpiDefinition) -> KPIResponse:
    return KPIResponse(
        id=k.id, name=k.name, display_name=k.display_name,
        description=k.description, formula=k.formula, unit=k.unit,
        aggregation_method=k.aggregation_method, display_format=k.display_format,
        domain=k.domain, is_active=k.is_active, is_system=k.is_system,
    )


def _glossary_response(g: BusinessGlossary) -> GlossaryResponse:
    return GlossaryResponse(
        id=g.id, term=g.term, definition=g.definition,
        domain=g.domain, is_ai_generated=g.is_ai_generated,
        approved_by=g.approved_by,
    )


def _rule_response(r: BusinessRule) -> BusinessRuleResponse:
    return BusinessRuleResponse(
        id=r.id, entity_id=r.entity_id, rule_name=r.rule_name,
        predicate_sql=r.predicate_sql, description=r.description,
        is_default=r.is_default, is_system=r.is_system, pack_source=r.pack_source,
    )
