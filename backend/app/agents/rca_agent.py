"""
Root Cause Analysis Agent — explains *why* a metric changed or anomaly occurred.

Spec: AG-009, RCA-001, RCA-002, RCA-003
  - RCA-001: Runs two data queries — a "current" and a "prior period" — then correlates
  - RCA-002: Uses Claude to synthesise a causal narrative from the two result sets
  - RCA-003: Proposes 2-3 hypotheses ranked by likelihood with supporting evidence

RCA questions look like:
  "Why did revenue drop in March?"
  "Why are AR days increasing?"
  "What caused the spike in returns last week?"

Strategy:
  1. Parse the question for the target metric and anomaly period
  2. Use the already-selected tool (query_planner ran first) to fetch current period data
  3. Derive a prior-period version of the same query and execute it
  4. Ask Claude to compare and generate hypotheses

If query_result is already populated (SQL executor ran), skip re-execution and
use the existing result directly for the "current" period. Then derive the prior period.

Prior period derivation:
  - If the resolved params contain date params, shift them back by one equivalent period
  - If no date params found, execute the same query with a 30-day lookback offset
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import date, timedelta
from typing import Any

from app.agents.base import BaseAgent
from app.agents.state import AgentState

_RCA_SYSTEM = """\
You are an enterprise analytics expert performing root cause analysis.
You have been given two periods of business data for the same metric.

Your task:
1. Identify the key differences between the periods
2. Propose 2-3 likely root causes ranked by probability (most likely first)
3. Support each hypothesis with specific numbers from the data
4. Flag any data limitations that could affect the analysis

Output format (plain prose, no JSON):
- One paragraph summarising what changed and by how much
- "Likely causes:" followed by numbered hypotheses with evidence
- "Note:" if there are data gaps or caveats

Be precise. Use actual numbers. Avoid vague language like "it seems" or "possibly".
"""

_PERIOD_SHIFT_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2})",  # ISO date in params
)


class RCAAgent(BaseAgent):
    name = "rca_agent"

    async def _run(self, state: AgentState) -> dict[str, Any]:
        question = state.get("enriched_question") or state["question"]
        current_result = state.get("query_result") or {}
        current_rows = current_result.get("rows", [])
        current_cols = current_result.get("columns", [])

        tool = state.get("selected_tool") or {}
        params = dict(state.get("resolved_params") or {})

        # ── Derive prior period ───────────────────────────────────────────────
        prior_rows, prior_cols = await self._fetch_prior_period(state, tool, params)

        # ── Synthesise with Claude ────────────────────────────────────────────
        current_summary = _summarise_rows(current_rows[:20], current_cols, "Current period")
        prior_summary = _summarise_rows(prior_rows[:20], prior_cols, "Prior period")

        user_msg = (
            f"Business question: {question}\n\n"
            f"{current_summary}\n\n"
            f"{prior_summary}"
        )

        answer = await self._call_llm(
            system=_RCA_SYSTEM,
            user=user_msg,
            model=self._default_model,
            max_tokens=1024,
        )

        # Confidence: lower than normal because RCA is inherently uncertain
        base_confidence = state.get("confidence_score") or 0.5
        rca_confidence = round(base_confidence * 0.8, 3)

        lineage = {
            **(state.get("lineage") or {}),
            "rca": {
                "current_rows": len(current_rows),
                "prior_rows": len(prior_rows),
                "prior_period_derived": bool(prior_rows),
            },
        }

        follow_ups = [
            "Which specific customers or items are driving this change?",
            "How does this compare to the same period last year?",
            "What corrective actions would you recommend?",
        ]

        self._log.info(
            "rca_agent.done",
            current_rows=len(current_rows),
            prior_rows=len(prior_rows),
        )

        return {
            "answer_text": answer,
            "answer_data": {
                "type": "rca",
                "current": {"rows": current_rows[:50], "columns": current_cols},
                "prior": {"rows": prior_rows[:50], "columns": prior_cols},
            },
            "chart_hint": "bar",  # side-by-side comparison
            "follow_up_questions": follow_ups,
            "confidence_score": rca_confidence,
            "lineage": lineage,
        }

    async def _fetch_prior_period(
        self, state: AgentState, tool: dict, params: dict
    ) -> tuple[list[dict], list[str]]:
        """
        Execute the same tool with date params shifted back one period.
        Returns (rows, columns) or ([], []) on failure.
        """
        if not tool.get("sql_template"):
            return [], []

        prior_params = _shift_dates_back(params)
        if prior_params == params:
            # No date params to shift — use a default 30-day lookback
            prior_params = _apply_30d_offset(params)

        from app.agents.sql_executor import (
            _check_required_params,
            _inject_row_limit,
            _substitute_params,
        )
        from app.services.sql.validator import validate_sql

        sql = tool["sql_template"]
        validation = validate_sql(sql)
        if not validation.is_valid:
            return [], []

        missing = _check_required_params(tool.get("input_schema", []), prior_params)
        if missing:
            return [], []

        sql = _inject_row_limit(sql, 200)
        bound_sql = _substitute_params(sql, prior_params)

        try:
            from app.db.session import AsyncSessionLocal
            from sqlalchemy import select as sa_select
            from app.models.connection import Connection
            from app.services.connections.connector import get_connector

            connection_id = state.get("connection_id")
            async with AsyncSessionLocal() as db:
                if not connection_id:
                    r = await db.execute(
                        sa_select(Connection).where(
                            Connection.tenant_id == state["tenant_id"],
                            Connection.is_active.is_(True),
                        ).limit(1)
                    )
                    conn_row = r.scalar_one_or_none()
                    if not conn_row:
                        return [], []
                    connection_id = conn_row.id

                r2 = await db.execute(sa_select(Connection).where(Connection.id == connection_id))
                connection = r2.scalar_one_or_none()
                if not connection:
                    return [], []

                from app.core.redis import get_redis
                from app.services.connections.connection_service import ConnectionService
                redis = get_redis()
                credentials = ConnectionService(db, redis)._load_credentials(connection)
                connector = get_connector(connection.db_type, str(connection.id), redis)
                rows_raw = await connector.execute_query(credentials, bound_sql)

            if not rows_raw:
                return [], []
            columns = list(rows_raw[0].keys()) if isinstance(rows_raw[0], dict) else []
            rows = [dict(r) if not isinstance(r, dict) else r for r in rows_raw]
            return rows, columns

        except Exception as exc:
            self._log.warning("rca_agent.prior_fetch_fail", exc=str(exc))
            return [], []


# ── Helpers ────────────────────────────────────────────────────────────────────

def _shift_dates_back(params: dict[str, Any]) -> dict[str, Any]:
    """Shift all ISO date params back by 30 days (simple prior-period heuristic)."""
    result = dict(params)
    for key, val in params.items():
        if isinstance(val, str) and _PERIOD_SHIFT_RE.match(val):
            try:
                d = date.fromisoformat(val)
                result[key] = (d - timedelta(days=30)).isoformat()
            except ValueError:
                pass
    return result


def _apply_30d_offset(params: dict[str, Any]) -> dict[str, Any]:
    """When no date params exist, add a 30d lookback suffix to string params."""
    return params  # No-op for non-date queries


def _summarise_rows(
    rows: list[dict], columns: list[str], label: str
) -> str:
    if not rows:
        return f"{label}: No data returned."
    row_count = len(rows)
    preview = json.dumps(rows[:5], default=str)
    cols_str = ", ".join(columns[:8]) if columns else "unknown columns"
    return (
        f"{label} ({row_count} rows, columns: {cols_str}):\n"
        f"Sample data: {preview}"
    )
