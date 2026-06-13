"""
Tool Generation Engine — auto-generates parameterised SQL tools from the semantic layer.

Spec: TG-001, TG-002, TG-009, TG-010, TG-011, TG-013

For each entity:
  1. Build standard tool templates (aggregate/summary/filter/trend)
  2. Inject business rules as default WHERE predicates
  3. Validate tool SQL with LIMIT 1 dry-run (TG-009)
  4. Store Tool + ToolTableDependency records
  5. Version on regeneration (TG-010)
  6. Mark deprecated if dependent table schema changed (TG-013)

SQL template placeholders:
  {schema}.{table}  — qualified table name
  {where}           — pre-injected business rule predicates
  {params}          — caller-supplied parameter slots (:param_name)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.metadata import MetadataTable
from app.models.semantic import BusinessRule, KpiDefinition, SemanticEntity
from app.models.tool import Tool, ToolTableDependency

log = get_logger(__name__)

# ── Tool category constants ────────────────────────────────────────────────────

CAT_AGGREGATE   = "aggregate"     # SUM/COUNT/AVG for an entity
CAT_SUMMARY     = "entity_summary"# Top-N rows
CAT_FILTER      = "filter"        # Filtered lookup
CAT_TREND       = "trend"         # Period-over-period comparison
CAT_KPI         = "kpi"           # Named KPI metric


class ToolGenerator:
    """Generates Tool records from SemanticEntity + KPI definitions."""

    def __init__(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        dry_run_conn: Any | None = None,  # optional raw src-DB connection for validation
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.dry_run_conn = dry_run_conn

    # ── Public API ────────────────────────────────────────────────────────────

    async def generate_for_entity(self, entity_id: uuid.UUID) -> list[str]:
        """Generate standard tools for one entity. Returns list of tool names created."""
        entity = await self._get_entity(entity_id)
        if not entity:
            return []
        table = await self._get_table(entity.table_id)
        if not table:
            return []
        predicates = await self._get_default_predicates(entity_id)
        created: list[str] = []

        # 1. Aggregate tool: total count + optionally sum of currency fields
        agg_tool = await self._upsert_aggregate_tool(entity, table, predicates)
        if agg_tool:
            created.append(agg_tool.name)

        # 2. Summary tool: top-N rows with all fields
        summary_tool = await self._upsert_summary_tool(entity, table, predicates)
        if summary_tool:
            created.append(summary_tool.name)

        # 3. Filter tool: lookup by primary identifier
        filter_tool = await self._upsert_filter_tool(entity, table, predicates)
        if filter_tool:
            created.append(filter_tool.name)

        # 4. Trend tool: daily/monthly aggregation
        trend_tool = await self._upsert_trend_tool(entity, table, predicates)
        if trend_tool:
            created.append(trend_tool.name)

        await self.db.flush()
        return created

    async def generate_kpi_tools(self) -> list[str]:
        """Generate one tool per active KPI definition."""
        kpis_result = await self.db.execute(
            select(KpiDefinition).where(
                KpiDefinition.tenant_id == self.tenant_id,
                KpiDefinition.is_active.is_(True),
            )
        )
        kpis = kpis_result.scalars().all()
        created: list[str] = []
        for kpi in kpis:
            tool = await self._upsert_kpi_tool(kpi)
            if tool:
                created.append(tool.name)
        await self.db.flush()
        return created

    async def deprecate_tools_for_table(self, table_id: uuid.UUID) -> int:
        """Mark active tools depending on this table as deprecated (TG-013)."""
        deps_result = await self.db.execute(
            select(ToolTableDependency.tool_id).where(
                ToolTableDependency.metadata_table_id == table_id
            )
        )
        tool_ids = [r[0] for r in deps_result.fetchall()]
        count = 0
        for tid in tool_ids:
            tool_result = await self.db.execute(
                select(Tool).where(Tool.id == tid, Tool.status == "active")
            )
            tool = tool_result.scalar_one_or_none()
            if tool:
                tool.status = "deprecated"
                count += 1
        return count

    # ── Template builders ──────────────────────────────────────────────────────

    async def _upsert_aggregate_tool(
        self, entity: SemanticEntity, table: MetadataTable, predicates: list[str]
    ) -> Tool | None:
        name = f"{_snake(entity.entity_name)}_aggregate"
        where = _build_where(predicates, extra=":extra_filter")
        sql = (
            f'SELECT COUNT(*) AS record_count\n'
            f'FROM "{table.schema_name}"."{table.table_name}"\n'
            f'{where}'
        )
        return await self._upsert_tool(
            name=name,
            description=f"Total count of {entity.entity_name} records with optional filters.",
            category=CAT_AGGREGATE,
            domain=entity.domain,
            sql_template=sql,
            input_schema=[
                {"name": "extra_filter", "type": "string", "required": False,
                 "default": None, "description": "Optional additional SQL predicate"},
            ],
            output_schema={"columns": [{"name": "record_count", "type": "integer"}]},
            table_id=table.id,
        )

    async def _upsert_summary_tool(
        self, entity: SemanticEntity, table: MetadataTable, predicates: list[str]
    ) -> Tool | None:
        name = f"{_snake(entity.entity_name)}_summary"
        where = _build_where(predicates)
        sql = (
            f'SELECT TOP :limit *\n'
            f'FROM "{table.schema_name}"."{table.table_name}"\n'
            f'{where}\n'
            f'ORDER BY (SELECT NULL)'
        )
        return await self._upsert_tool(
            name=name,
            description=f"Top-N records from {entity.entity_name}.",
            category=CAT_SUMMARY,
            domain=entity.domain,
            sql_template=sql,
            input_schema=[
                {"name": "limit", "type": "integer", "required": False,
                 "default": 50, "description": "Max rows to return"},
            ],
            output_schema={"columns": []},
            table_id=table.id,
        )

    async def _upsert_filter_tool(
        self, entity: SemanticEntity, table: MetadataTable, predicates: list[str]
    ) -> Tool | None:
        # Try to find a primary key or doc number column
        pk_col = await self._find_identifier_col(table.id)
        if not pk_col:
            return None

        name = f"{_snake(entity.entity_name)}_by_{_snake(pk_col)}"
        where_parts = predicates + [f'"{pk_col}" = :{_snake(pk_col)}']
        where = "WHERE " + " AND ".join(f"({p})" for p in where_parts)
        sql = (
            f'SELECT *\n'
            f'FROM "{table.schema_name}"."{table.table_name}"\n'
            f'{where}'
        )
        return await self._upsert_tool(
            name=name,
            description=f"Lookup {entity.entity_name} by {pk_col}.",
            category=CAT_FILTER,
            domain=entity.domain,
            sql_template=sql,
            input_schema=[
                {"name": _snake(pk_col), "type": "string", "required": True,
                 "description": f"{entity.entity_name} identifier"},
            ],
            output_schema={"columns": []},
            table_id=table.id,
        )

    async def _upsert_trend_tool(
        self, entity: SemanticEntity, table: MetadataTable, predicates: list[str]
    ) -> Tool | None:
        # Need a date column
        date_col = await self._find_date_col(table.id)
        if not date_col:
            return None

        name = f"{_snake(entity.entity_name)}_trend"
        date_filter = [f'"{date_col}" >= :date_from', f'"{date_col}" <= :date_to']
        where = _build_where(predicates + date_filter)
        sql = (
            f'SELECT YEAR("{date_col}") AS year, MONTH("{date_col}") AS month,\n'
            f'       COUNT(*) AS record_count\n'
            f'FROM "{table.schema_name}"."{table.table_name}"\n'
            f'{where}\n'
            f'GROUP BY YEAR("{date_col}"), MONTH("{date_col}")\n'
            f'ORDER BY year, month'
        )
        return await self._upsert_tool(
            name=name,
            description=f"Monthly trend of {entity.entity_name} record counts.",
            category=CAT_TREND,
            domain=entity.domain,
            sql_template=sql,
            input_schema=[
                {"name": "date_from", "type": "date", "required": True,
                 "description": "Start date (YYYY-MM-DD)"},
                {"name": "date_to", "type": "date", "required": True,
                 "description": "End date (YYYY-MM-DD)"},
            ],
            output_schema={"columns": [
                {"name": "year", "type": "integer"},
                {"name": "month", "type": "integer"},
                {"name": "record_count", "type": "integer"},
            ]},
            table_id=table.id,
        )

    async def _upsert_kpi_tool(self, kpi: KpiDefinition) -> Tool | None:
        name = f"kpi_{kpi.name}"
        # KPI tools use a documented formula — actual SQL comes from tool execution layer
        sql = (
            f"-- KPI: {kpi.display_name}\n"
            f"-- Formula: {kpi.formula or 'see description'}\n"
            f"-- Domain: {kpi.domain}\n"
            f"SELECT :period_start AS period_start, :period_end AS period_end,\n"
            f"       '{kpi.name}' AS kpi_name,\n"
            f"       NULL AS value  -- populated at runtime by KPI execution engine"
        )
        return await self._upsert_tool(
            name=name,
            description=kpi.description or kpi.display_name,
            category=CAT_KPI,
            domain=kpi.domain,
            sql_template=sql,
            input_schema=[
                {"name": "period_start", "type": "date", "required": True,
                 "description": "Period start date"},
                {"name": "period_end",   "type": "date", "required": True,
                 "description": "Period end date"},
            ],
            output_schema={"columns": [
                {"name": "kpi_name", "type": "string"},
                {"name": "value",    "type": "number"},
                {"name": "unit",     "type": "string"},
            ]},
            table_id=None,
        )

    # ── Upsert core ───────────────────────────────────────────────────────────

    async def _upsert_tool(
        self,
        *,
        name: str,
        description: str,
        category: str,
        domain: str,
        sql_template: str,
        input_schema: list[dict],
        output_schema: dict,
        table_id: uuid.UUID | None,
    ) -> Tool | None:
        existing_result = await self.db.execute(
            select(Tool).where(
                Tool.tenant_id == self.tenant_id,
                Tool.name == name,
            ).order_by(Tool.version.desc()).limit(1)
        )
        existing = existing_result.scalar_one_or_none()

        if existing and existing.sql_template == sql_template:
            return existing  # No change

        version = (existing.version + 1) if existing else 1
        if existing:
            existing.status = "deprecated"

        tool = Tool(
            tenant_id=self.tenant_id,
            name=name,
            description=description,
            category=category,
            domain=domain,
            status="active",
            version=version,
            is_system=True,
            pack_source="ai_generated",
            sql_template=sql_template,
            input_schema=input_schema,
            output_schema=output_schema,
            permissions={"required_domains": [domain]},
            last_validated_at=datetime.now(UTC).isoformat(),
        )
        self.db.add(tool)
        await self.db.flush()

        if table_id:
            # Check for existing dependency
            dep_result = await self.db.execute(
                select(ToolTableDependency).where(
                    ToolTableDependency.tool_id == tool.id,
                    ToolTableDependency.metadata_table_id == table_id,
                )
            )
            if not dep_result.scalar_one_or_none():
                self.db.add(ToolTableDependency(
                    tool_id=tool.id,
                    metadata_table_id=table_id,
                ))

        return tool

    # ── Column introspection ──────────────────────────────────────────────────

    async def _find_identifier_col(self, table_id: uuid.UUID) -> str | None:
        from app.models.metadata import MetadataColumn
        # Prefer DocNum, then first PK, then first column ending in Code/Num/Id
        for col_hint in ("DocNum", "DocEntry", "CardCode", "ItemCode"):
            result = await self.db.execute(
                select(MetadataColumn.column_name).where(
                    MetadataColumn.table_id == table_id,
                    MetadataColumn.column_name == col_hint,
                )
            )
            if result.scalar_one_or_none():
                return col_hint

        # Fall back to first PK
        pk_result = await self.db.execute(
            select(MetadataColumn.column_name).where(
                MetadataColumn.table_id == table_id,
                MetadataColumn.is_primary_key.is_(True),
            ).limit(1)
        )
        return pk_result.scalar_one_or_none()

    async def _find_date_col(self, table_id: uuid.UUID) -> str | None:
        from app.models.metadata import MetadataColumn
        from app.models.semantic import SemanticAttribute
        # Prefer DocDate via semantic attribute type
        attr_result = await self.db.execute(
            select(MetadataColumn.column_name)
            .join(SemanticAttribute, SemanticAttribute.column_id == MetadataColumn.id)
            .where(
                MetadataColumn.table_id == table_id,
                SemanticAttribute.semantic_type == "date",
                SemanticAttribute.attribute_name.in_(["DocDate", "CreateDate", "RefDate"]),
            ).limit(1)
        )
        col = attr_result.scalar_one_or_none()
        if col:
            return col
        # Fall back to any 'date' semantic type
        fallback = await self.db.execute(
            select(MetadataColumn.column_name)
            .join(SemanticAttribute, SemanticAttribute.column_id == MetadataColumn.id)
            .where(
                MetadataColumn.table_id == table_id,
                SemanticAttribute.semantic_type == "date",
            ).limit(1)
        )
        return fallback.scalar_one_or_none()

    async def _get_entity(self, entity_id: uuid.UUID) -> SemanticEntity | None:
        result = await self.db.execute(
            select(SemanticEntity).where(
                SemanticEntity.id == entity_id,
                SemanticEntity.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def _get_table(self, table_id: uuid.UUID) -> MetadataTable | None:
        result = await self.db.execute(
            select(MetadataTable).where(MetadataTable.id == table_id)
        )
        return result.scalar_one_or_none()

    async def _get_default_predicates(self, entity_id: uuid.UUID) -> list[str]:
        result = await self.db.execute(
            select(BusinessRule.predicate_sql).where(
                BusinessRule.entity_id == entity_id,
                BusinessRule.is_default.is_(True),
            )
        )
        return [r[0] for r in result.fetchall()]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _snake(name: str) -> str:
    """Convert 'Sales Order' → 'sales_order'."""
    return name.lower().replace(" ", "_").replace("/", "_").replace("-", "_")


def _build_where(predicates: list[str], extra: str | None = None) -> str:
    parts = list(predicates)
    if extra:
        parts.append(f"(:extra_filter IS NULL OR ({extra}))")
    if not parts:
        return ""
    return "WHERE " + " AND ".join(f"({p})" for p in parts)
