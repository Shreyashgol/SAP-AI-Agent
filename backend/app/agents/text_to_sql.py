"""
Text-to-SQL Agent — runtime fallback when no curated tool matches a question.

When the Query Planner finds no tool for a question, rather than erroring out we
generate a SELECT directly from the crawled schema catalog. The generated SQL is
guarded twice before it ever runs:

  1. catalog validation — every table/column it references must exist in the
     crawled metadata (reuses AISchemaGenerator._validate_sql), so a phantom
     table/column can never reach the database.
  2. DML/AST validation — validate_sql() blocks anything that isn't a SELECT.

On success it writes a synthetic `selected_tool` (with the generated SQL as the
template and no parameters), so the existing sql_executor → response_formatter
path runs unchanged. On failure it sets `error`, which routes to error_handler.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.agents.base import BaseAgent
from app.agents.state import AgentState

_SYSTEM = """\
You are an expert T-SQL analyst for a Microsoft SQL Server database (a SAP
Business One company database). Given a business question and the database
schema, write ONE valid T-SQL SELECT query that answers it.

Rules:
- Output ONLY the SQL query — no prose, no markdown fences, no explanation.
- SELECT statements ONLY. Never write INSERT/UPDATE/DELETE/DROP/ALTER/etc.
- Use ONLY tables and columns that appear in the provided schema. Never invent
  table or column names. If the schema cannot answer the question, return the
  single word: NONE
- T-SQL syntax: limit rows with "SELECT TOP N" (never LIMIT), use GETDATE() for
  the current date, and standard T-SQL date functions.
- Resolve relative dates ("this year", "last quarter", "recently", "YTD")
  against TODAY'S DATE provided below — never guess the year.
- Prefer explicit column lists over SELECT *.
- Join tables using the provided foreign-key relationships.
- For "top N" / ranking questions, include ORDER BY and SELECT TOP N.
"""


class TextToSQLAgent(BaseAgent):
    name = "text_to_sql"

    async def _run(self, state: AgentState) -> dict[str, Any]:
        from app.db.session import AsyncSessionLocal
        from app.services.semantic.ai_generator import AISchemaGenerator
        from app.services.sql.validator import validate_sql

        question = state.get("enriched_question") or state["question"]
        tenant_id = state["tenant_id"]

        async with AsyncSessionLocal() as db:
            connection_id = await self._resolve_connection_id(db, state)
            if not connection_id:
                return {"error": "No active database connection found for this tenant.",
                        "fallback_used": True}

            gen = AISchemaGenerator(db, tenant_id)
            tables = await gen._load_tables(connection_id)
            if not tables:
                return {"error": "No schema catalog is available to answer this question. "
                                 "Run discovery on the connection first.",
                        "fallback_used": True}

            cols_by_table, known_columns, table_name_to_id = await gen._load_columns(tables)
            relations = await gen._load_relations(tables, cols_by_table)
            known_tables = set(table_name_to_id.keys())

            schema_text = _build_schema_text(tables, cols_by_table)
            fk_text = "\n".join(relations) or "(none discovered)"
            today = date.today().isoformat()
            user_msg = (
                f"TODAY'S DATE: {today}\n\n"
                f"DATABASE SCHEMA (table(columns)):\n{schema_text}\n\n"
                f"FOREIGN KEYS:\n{fk_text}\n\n"
                f"QUESTION: {question}\n\n"
                f"Write the T-SQL SELECT query:"
            )

            # Use the stronger default model — SQL generation needs the accuracy.
            raw = await self._call_llm(
                system=_SYSTEM, user=user_msg, model=self._default_model, max_tokens=800
            )
            sql = _clean_sql(raw)

            if not sql or sql.upper() == "NONE":
                return {
                    "error": "No tool matches this question against the available data, "
                             "and it could not be answered from the connected schema.",
                    "fallback_used": True,
                }

            # Guard 1 — DML/AST: SELECT only.
            v = validate_sql(sql)
            if not v.is_valid:
                self._log.warning("text_to_sql.dml_blocked", error=v.error)
                return {"error": f"Generated query was blocked: {v.error}", "fallback_used": True}

            # Guard 2 — catalog: no phantom tables/columns.
            ok, reason, ref_tables = gen._validate_sql(sql, known_tables, known_columns)
            if not ok:
                self._log.warning("text_to_sql.catalog_reject", reason=reason, sql=sql[:200])
                return {
                    "error": "Could not generate a reliable query for this question "
                             "from the connected schema.",
                    "fallback_used": True,
                }

        self._log.info("text_to_sql.generated", tables=sorted(ref_tables), sql=sql[:200])
        return {
            "selected_tool": {
                "tool_id": None,
                "name": "ad_hoc_text_to_sql",
                "description": "Ad-hoc SQL generated from the question and schema.",
                "category": "custom",
                "domain": state.get("detected_domain") or "general",
                "sql_template": sql,
                "input_schema": [],
            },
            "resolved_params": {},
            "fallback_used": True,
            "lineage": {
                **(state.get("lineage") or {}),
                "text_to_sql": True,
                "tables_used": sorted(ref_tables),
            },
        }

    @staticmethod
    async def _resolve_connection_id(db: Any, state: AgentState) -> Any:
        """Use the state's connection, else the tenant's first active connection."""
        connection_id = state.get("connection_id")
        if connection_id:
            return connection_id
        from sqlalchemy import select
        from app.models.connection import Connection
        result = await db.execute(
            select(Connection.id).where(
                Connection.tenant_id == state["tenant_id"],
                Connection.is_active.is_(True),
            ).limit(1)
        )
        return result.scalar_one_or_none()


def _build_schema_text(tables: list, cols_by_table: dict) -> str:
    """Compact `- table(col type PK, ...)  -- description` lines for the prompt."""
    lines: list[str] = []
    for t in tables:
        col_descs = []
        for c in cols_by_table.get(t.id, []):
            d = f"{c.column_name} {c.data_type}"
            if c.is_primary_key:
                d += " PK"
            col_descs.append(d)
        line = f"- {t.table_name}({', '.join(col_descs)})"
        if t.ai_description:
            line += f"  -- {t.ai_description}"
        lines.append(line)
    return "\n".join(lines)


def _clean_sql(raw: str) -> str:
    """Strip markdown fences/prose and return the SQL starting at SELECT/WITH."""
    s = (raw or "").strip()
    fence = re.search(r"```(?:sql)?\s*(.*?)```", s, re.DOTALL | re.IGNORECASE)
    if fence:
        s = fence.group(1).strip()
    start = re.search(r"\b(SELECT|WITH)\b", s, re.IGNORECASE)
    if start:
        s = s[start.start():]
    return s.strip().rstrip(";").strip()
