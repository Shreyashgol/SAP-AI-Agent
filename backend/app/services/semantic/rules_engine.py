"""
Business rules engine — applies default predicates to entity queries.

Default rules are injected as WHERE clause fragments into SQL generation.
Only rules where is_default=True are applied automatically (SL-007).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.semantic import BusinessRule, SemanticEntity


class BusinessRulesEngine:
    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        # {entity_id → [predicate_sql, ...]}
        self._cache: dict[uuid.UUID, list[str]] | None = None

    async def get_predicates_for_entity(
        self, entity_id: uuid.UUID, default_only: bool = True
    ) -> list[str]:
        """Return list of SQL predicate strings for the given entity."""
        await self._ensure_cache(default_only)
        return self._cache.get(entity_id, [])  # type: ignore[return-value]

    async def get_predicates_for_table(
        self, table_id: uuid.UUID, default_only: bool = True
    ) -> list[str]:
        """Resolve entity by table_id and return its predicates."""
        result = await self.db.execute(
            select(SemanticEntity).where(
                SemanticEntity.tenant_id == self.tenant_id,
                SemanticEntity.table_id == table_id,
            )
        )
        entity = result.scalar_one_or_none()
        if not entity:
            return []
        return await self.get_predicates_for_entity(entity.id, default_only)

    async def build_where_clause(
        self, entity_id: uuid.UUID, extra_predicates: list[str] | None = None
    ) -> str:
        """
        Combine default rules + any extra predicates into a WHERE clause.
        Returns empty string if no rules apply.
        """
        predicates = await self.get_predicates_for_entity(entity_id)
        if extra_predicates:
            predicates = predicates + extra_predicates
        if not predicates:
            return ""
        return "WHERE " + " AND ".join(f"({p})" for p in predicates)

    def invalidate_cache(self) -> None:
        self._cache = None

    async def _ensure_cache(self, default_only: bool = True) -> None:
        if self._cache is not None:
            return
        q = select(BusinessRule).where(
            BusinessRule.tenant_id == self.tenant_id
        )
        if default_only:
            q = q.where(BusinessRule.is_default.is_(True))

        result = await self.db.execute(q)
        cache: dict[uuid.UUID, list[str]] = {}
        for rule in result.scalars().all():
            cache.setdefault(rule.entity_id, []).append(rule.predicate_sql)
        self._cache = cache
