"""
Query Planner Agent — maps intent + entities to a ranked tool + bound parameters.

Spec: AG-004, QP-001, QP-002, QP-003, QP-004

Steps:
  1. VectorSearch → top-5 tool candidates (ranked by ToolRanker)
  2. Select best tool (highest final_score)
  3. Extract parameter values from the question via Claude
  4. KG traversal if multi-entity query requires JOINs
  5. Output: selected_tool, resolved_params, join_path, entity_ids

Parameter extraction prompt uses the tool's input_schema as a guide.
Missing required parameters get a None value — the SQL Executor will request clarification.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from app.agents.base import BaseAgent
from app.agents.state import AgentState

_PARAM_SYSTEM = """\
You are a parameter extraction assistant. Given a business question and a list of
SQL tool parameters, extract the values from the question.

Output ONLY valid JSON — no prose, no markdown.

Rules:
- Dates must be in YYYY-MM-DD format
- Resolve relative dates ("this year", "last quarter", "recently", "YTD") against
  TODAY'S DATE provided below — never guess the year
- If a value cannot be determined from the question, use null
- Do not invent values not present in the question
- For "top N" requests, extract the limit number; default to 10 if unspecified

Output: {"param_name": value, ...}
"""

# Param-name fragments that mark the start vs. end of a date range
_DATE_FROM_HINTS = ("from", "start", "since", "begin", "after")
_DATE_TO_HINTS = ("to", "end", "until", "thru", "through", "as_of", "asof", "before")


class QueryPlannerAgent(BaseAgent):
    name = "query_planner"

    async def _run(self, state: AgentState) -> dict[str, Any]:
        from app.db.session import AsyncSessionLocal
        from app.services.tools.ranker import ToolRanker
        from app.services.knowledge_graph.traversal import GraphTraversal
        from app.services.embedding.vector_search import VectorSearchService

        # Use the context-resolved question (ContextAgent rewrites follow-ups
        # like "show the top 3 of those" into a self-contained question). The
        # raw question alone has no business content for the ranker.
        question = state.get("enriched_question") or state["question"]
        tenant_id = state["tenant_id"]
        domain = state.get("detected_domain")

        async with AsyncSessionLocal() as db:
            # Step 1 — rank tools
            ranker = ToolRanker(db, tenant_id)
            ranked = await ranker.rank(question, detected_domain=domain, top_k=5)

            if not ranked:
                # No curated tool matches. Rather than giving up, fall back to the
                # text-to-SQL agent, which generates a SELECT directly from the
                # crawled schema catalog (validated against it). The supervisor
                # routes a tool-less planner result with this flag to text_to_sql.
                self._log.info(
                    "query_planner.no_tool_fallback_text_to_sql", question=question[:80]
                )
                return {
                    "candidate_tools": [],
                    "selected_tool": None,
                    "use_text_to_sql": True,
                }

            # Step 2 — store candidates for lineage
            candidates = [
                {
                    "tool_id": str(r.tool_id),
                    "name": r.tool_name,
                    "score": r.final_score,
                    "domain": r.domain,
                    "category": r.category,
                }
                for r in ranked
            ]

            # Step 3 — load best tool's full record
            from sqlalchemy import select
            from app.models.tool import Tool
            best = ranked[0]
            tool_result = await db.execute(
                select(Tool).where(Tool.id == best.tool_id)
            )
            tool = tool_result.scalar_one_or_none()
            if not tool:
                return {"error": "Selected tool record not found.", "candidate_tools": candidates}

            # Step 4 — extract parameters
            resolved = await self._extract_params(question, tool)

            # Step 5 — KG join path (for Trend/Comparative that need multi-entity)
            join_path: str | None = None
            entity_ids: list[uuid.UUID] = []

            from app.models.metadata import MetadataTable
            from app.models.semantic import SemanticEntity
            from sqlalchemy import select as sa_select
            entity_result = await db.execute(
                sa_select(SemanticEntity.id)
                .join(MetadataTable, MetadataTable.id == SemanticEntity.table_id)
                .where(
                    SemanticEntity.tenant_id == tenant_id,
                )
                .limit(1)
            )
            primary_entity = entity_result.scalar_one_or_none()
            if primary_entity:
                entity_ids = [primary_entity]

            selected_tool_dict = {
                "tool_id": str(tool.id),
                "name": tool.name,
                "description": tool.description,
                "category": tool.category,
                "domain": tool.domain,
                "sql_template": tool.sql_template,
                "input_schema": tool.input_schema,
            }

        self._log.info("query_planner.selected",
                       tool=tool.name, params=list(resolved.keys()))
        return {
            "candidate_tools": candidates,
            "selected_tool": selected_tool_dict,
            "resolved_params": resolved,
            "join_path": join_path,
            "entity_ids": entity_ids,
        }

    async def _extract_params(self, question: str, tool: Any) -> dict[str, Any]:
        """Ask Claude to extract parameter values from the question."""
        schema = tool.input_schema or []
        if not schema:
            return {}

        params_desc = "\n".join(
            f"- {p['name']} ({p['type']}, {'required' if p.get('required') else 'optional'}): {p.get('description', '')}"
            for p in schema
        )
        today = date.today().isoformat()
        user_msg = (
            f"TODAY'S DATE: {today}\n\n"
            f"Question: {question}\n\nParameters to extract:\n{params_desc}"
        )

        raw = await self._call_llm(system=_PARAM_SYSTEM, user=user_msg)
        parsed = self._extract_json(raw)
        if not parsed:
            self._log.warning("query_planner.param_extraction_fail", raw=raw[:200])
            parsed = {}

        # Type coercion
        result: dict[str, Any] = {}
        for param in schema:
            name = param["name"]
            val = parsed.get(name)
            if val is None:
                result[name] = None
                continue
            ptype = param.get("type", "string")
            try:
                if ptype == "integer":
                    result[name] = int(val)
                elif ptype == "number":
                    result[name] = float(val)
                else:
                    result[name] = str(val)
            except (ValueError, TypeError):
                result[name] = val

        # Default any still-missing date-range param to an all-time window so
        # undated questions ("compare sales by city") return data instead of
        # bouncing to clarification. Non-date params (e.g. a "threshold") still
        # fall through to clarification when required and unresolved.
        _apply_date_defaults(schema, result, today)
        return result


def _apply_date_defaults(
    schema: list[dict], params: dict[str, Any], today: str
) -> None:
    """Fill missing date-range params in place: 'from' side → all-time start,
    'to'/'as-of' side → today. Mutates `params`."""
    for param in schema:
        name = param["name"]
        if params.get(name) is not None:
            continue
        lname = name.lower()
        is_date = param.get("type") == "date" or any(
            tok in lname for tok in ("date", "period", "year", "month")
        )
        if not is_date:
            continue
        if any(h in lname for h in _DATE_FROM_HINTS):
            params[name] = "1900-01-01"
        elif any(h in lname for h in _DATE_TO_HINTS):
            params[name] = today
        else:
            params[name] = today
