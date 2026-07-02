"""
AI schema generator — Claude generates KPIs and query tools from the ACTUAL
crawled schema of a connection, instead of a hardcoded ERP pack.

Why this exists: a static SAP B1 pack assumes columns like Cancelled / DocNum /
OACT that may not exist in a given customer database, so its SQL fails at runtime.
Here Claude is given the real tables/columns/samples and asked to produce SQL
grounded only in what exists; every generated tool is then validated against the
crawled catalog (and reject-on-parse-failure) so a phantom column can never ship.

Model: claude-opus-4-8 (settings.anthropic_generation_model). Requires ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import json
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.settings import get_settings
from app.models.metadata import MetadataColumn, MetadataRelation, MetadataTable
from app.models.semantic import KpiDefinition
from app.models.tool import Tool, ToolTableDependency

log = get_logger(__name__)
settings = get_settings()

VALID_DOMAINS = ["finance", "sales", "purchasing", "inventory", "operations"]
_PLACEHOLDER_RE = re.compile(r":\w+")

_SYSTEM_PROMPT = """\
You are a senior ERP data analyst and Microsoft SQL Server (T-SQL) engineer.
You are given the REAL schema of a customer database — its tables, columns, data
types, and sample values. Produce useful business KPIs and parameterised SQL query
tools grounded ONLY in this schema.

HARD RULES (a violation makes the output unusable):
- Reference ONLY tables and columns that appear in the provided schema. Never invent
  columns (e.g. do NOT assume Cancelled, DocStatus, DocNum, OACT unless they are listed).
- Write valid T-SQL: use `SELECT TOP :limit`, never `LIMIT`; quote identifiers with
  [brackets]; use the schema-qualified name [schema].[table].
- Parameterise every user input as a named placeholder `:param_name` (e.g. :date_from,
  :card_code, :limit). Do not inline literals the user would choose.
- Prefer JOINs that follow the listed foreign-key relationships.
- Keep each tool focused and genuinely useful (top-N, aggregates, trends, lookups,
  reconciliations). Cover the main business questions the schema can answer.

Respond ONLY with a single valid JSON object, no prose, matching:
{
  "kpis": [
    {"name": "snake_case_id", "display_name": "Human Name",
     "description": "what it measures", "formula": "plain-English or pseudo-SQL formula",
     "unit": "currency|percent|number|count",
     "aggregation_method": "sum|avg|count|ratio|min|max",
     "display_format": "currency|percent|number|integer",
     "domain": "finance|sales|purchasing|inventory|operations"}
  ],
  "tools": [
    {"name": "snake_case_id", "description": "what question it answers",
     "category": "aggregate|filter|summary|trend|join|kpi",
     "domain": "finance|sales|purchasing|inventory|operations",
     "sql_template": "T-SQL using :params and [schema].[table]",
     "input_schema": [{"name": "param", "type": "string|date|integer|number",
                        "required": true, "description": "..."}],
     "output_schema": {"columns": [{"name": "col", "type": "string|number|date|integer"}]}}
  ]
}
"""


class AISchemaGenerator:
    """Generates KPIs + tools from a connection's crawled schema using Claude."""

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id

    async def generate(self, connection_id: uuid.UUID) -> dict[str, int]:
        tables = await self._load_tables(connection_id)
        if not tables:
            log.info("ai_generator.no_tables", connection_id=str(connection_id))
            return {"kpis": 0, "tools": 0, "rejected": 0}

        cols_by_table, known_columns, table_name_to_id = await self._load_columns(tables)
        known_tables = {t.table_name.lower() for t in tables}
        relations = await self._load_relations(tables, cols_by_table)

        context = self._build_context(tables, cols_by_table, relations)
        result = await self._call_claude(context)
        if not result:
            return {"kpis": 0, "tools": 0, "rejected": 0}

        kpis_made = await self._persist_kpis(result.get("kpis", []))
        tools_made, rejected = await self._persist_tools(
            result.get("tools", []), known_tables, known_columns, table_name_to_id
        )
        await self.db.flush()
        log.info("ai_generator.done", kpis=kpis_made, tools=tools_made, rejected=rejected)
        return {"kpis": kpis_made, "tools": tools_made, "rejected": rejected}

    # ── Schema loading ────────────────────────────────────────────────────────

    async def _load_tables(self, connection_id: uuid.UUID) -> list[MetadataTable]:
        res = await self.db.execute(
            select(MetadataTable).where(
                MetadataTable.tenant_id == self.tenant_id,
                MetadataTable.connection_id == connection_id,
                MetadataTable.is_system_table.is_(False),
            )
        )
        return list(res.scalars().all())

    async def _load_columns(
        self, tables: list[MetadataTable]
    ) -> tuple[dict[uuid.UUID, list[MetadataColumn]], set[str], dict[str, uuid.UUID]]:
        table_ids = [t.id for t in tables]
        res = await self.db.execute(
            select(MetadataColumn)
            .where(MetadataColumn.table_id.in_(table_ids))
            .order_by(MetadataColumn.ordinal_position)
        )
        cols_by_table: dict[uuid.UUID, list[MetadataColumn]] = {}
        known_columns: set[str] = set()
        for c in res.scalars().all():
            cols_by_table.setdefault(c.table_id, []).append(c)
            known_columns.add(c.column_name.lower())
        table_name_to_id = {t.table_name.lower(): t.id for t in tables}
        return cols_by_table, known_columns, table_name_to_id

    async def _load_relations(
        self, tables: list[MetadataTable], cols_by_table: dict[uuid.UUID, list[MetadataColumn]]
    ) -> list[str]:
        table_ids = [t.id for t in tables]
        res = await self.db.execute(
            select(MetadataRelation).where(MetadataRelation.from_table_id.in_(table_ids))
        )
        tbl_by_id = {t.id: t.table_name for t in tables}
        col_by_id = {c.id: c.column_name for cols in cols_by_table.values() for c in cols}
        hints: list[str] = []
        for r in res.scalars().all():
            ft, tt = tbl_by_id.get(r.from_table_id), tbl_by_id.get(r.to_table_id)
            fc, tc = col_by_id.get(r.from_column_id), col_by_id.get(r.to_column_id)
            if ft and tt and fc and tc:
                hint = f"{ft}.{fc} -> {tt}.{tc}"
                if r.notes:
                    hint += f"  -- {r.notes}"
                hints.append(hint)
        return hints

    def _build_context(
        self,
        tables: list[MetadataTable],
        cols_by_table: dict[uuid.UUID, list[MetadataColumn]],
        relations: list[str],
    ) -> str:
        schema: list[dict] = []
        for t in tables:
            cols = []
            for c in cols_by_table.get(t.id, []):
                entry: dict = {"name": c.column_name, "type": c.data_type}
                if c.is_primary_key:
                    entry["pk"] = True
                if c.is_foreign_key:
                    entry["fk"] = True
                if c.sample_values and not c.is_pii_flagged:
                    samples = (c.sample_values.get("values") or [])[:3]
                    if samples:
                        entry["samples"] = samples
                cols.append(entry)
            schema.append({
                "schema": t.schema_name,
                "table": t.table_name,
                "description": t.ai_description or "",
                "columns": cols,
            })
        payload = {"tables": schema, "foreign_keys": relations}
        return (
            "Here is the database schema. Generate KPIs and tools grounded ONLY in it.\n\n"
            + json.dumps(payload, indent=2, default=str)
        )

    # ── Claude ────────────────────────────────────────────────────────────────

    async def _call_claude(self, user_message: str) -> dict | None:
        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            message = await client.messages.create(
                model=settings.anthropic_generation_model,
                max_tokens=16000,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            raw = next((b.text for b in message.content if b.type == "text"), "").strip()
            if raw.startswith("```"):
                raw = raw.split("```", 2)[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except Exception as exc:
            log.warning("ai_generator.claude_error", error=str(exc))
            return None

    # ── Persistence ───────────────────────────────────────────────────────────

    async def _persist_kpis(self, kpis: list[dict]) -> int:
        existing = await self._existing_names(KpiDefinition.name, KpiDefinition)
        made = 0
        for k in kpis:
            name = (k.get("name") or "").strip()
            if not name or name in existing:
                continue
            self.db.add(KpiDefinition(
                tenant_id=self.tenant_id,
                name=name,
                display_name=k.get("display_name", name),
                description=k.get("description"),
                formula=k.get("formula"),
                unit=k.get("unit"),
                aggregation_method=k.get("aggregation_method", "sum"),
                display_format=k.get("display_format"),
                domain=k.get("domain") if k.get("domain") in VALID_DOMAINS else "operations",
                is_active=True,
                is_system=False,
            ))
            existing.add(name)
            made += 1
        return made

    async def _persist_tools(
        self,
        tools: list[dict],
        known_tables: set[str],
        known_columns: set[str],
        table_name_to_id: dict[str, uuid.UUID],
    ) -> tuple[int, int]:
        existing = await self._existing_names(Tool.name, Tool)
        made, rejected = 0, 0
        for t in tools:
            name = (t.get("name") or "").strip()
            sql = (t.get("sql_template") or "").strip()
            if not name or not sql or name in existing:
                continue
            ok, reason, ref_tables = self._validate_sql(sql, known_tables, known_columns)
            if not ok:
                rejected += 1
                log.info("ai_generator.tool_rejected", tool=name, reason=reason)
                continue
            tool = Tool(
                tenant_id=self.tenant_id,
                name=name,
                description=t.get("description", name),
                category=t.get("category", "aggregate"),
                domain=t.get("domain") if t.get("domain") in VALID_DOMAINS else "operations",
                sql_template=sql,
                input_schema=t.get("input_schema") or [],
                output_schema=t.get("output_schema") or {"columns": []},
                pack_source="ai_generated",
                is_system=False,
                status="active",
            )
            self.db.add(tool)
            await self.db.flush()
            for tname in ref_tables:
                tid = table_name_to_id.get(tname)
                if tid:
                    self.db.add(ToolTableDependency(tool_id=tool.id, metadata_table_id=tid))
            existing.add(name)
            made += 1
        return made, rejected

    async def _existing_names(self, column, model) -> set[str]:
        res = await self.db.execute(
            select(column).where(model.tenant_id == self.tenant_id)
        )
        return {r[0] for r in res.fetchall()}

    # ── SQL validation against the real catalog ───────────────────────────────

    def _validate_sql(
        self, sql: str, known_tables: set[str], known_columns: set[str]
    ) -> tuple[bool, str, set[str]]:
        """Reject SQL that references any table/column absent from the crawled schema.
        This is the guard that prevents phantom-column SQL (the Cancelled/DocNum class
        of failure) from ever being persisted."""
        try:
            import sqlglot
            from sqlglot import exp
        except Exception:
            return False, "sqlglot unavailable", set()

        probe = _PLACEHOLDER_RE.sub("0", sql)  # named params -> harmless literal for parsing
        try:
            tree = sqlglot.parse_one(probe, read="tsql")
        except Exception as exc:
            return False, f"unparseable: {exc}", set()
        if tree is None:
            return False, "empty parse", set()

        # SELECT aliases are valid names to reference downstream (ORDER BY total_revenue)
        aliases = {a.alias_or_name.lower() for a in tree.find_all(exp.Alias) if a.alias_or_name}

        ref_tables: set[str] = set()
        for tbl in tree.find_all(exp.Table):
            tname = (tbl.name or "").lower()
            if not tname:
                continue
            if tname not in known_tables:
                return False, f"unknown table: {tbl.name}", set()
            ref_tables.add(tname)

        for col in tree.find_all(exp.Column):
            cname = (col.name or "").lower()
            if not cname or cname == "*":
                continue
            if cname not in known_columns and cname not in aliases:
                return False, f"unknown column: {col.name}", set()

        return True, "", ref_tables
