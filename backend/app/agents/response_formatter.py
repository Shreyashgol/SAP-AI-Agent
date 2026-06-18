"""
Response Formatter Agent — translates raw query results into a structured answer.

Spec: AG-006, RF-001, RF-002, RF-003, RF-004
  - RF-001: answer_text — one-paragraph natural language narrative
  - RF-002: chart_hint — bar|line|area|donut|waterfall|kpi_card|table
  - RF-003: follow_up_questions — 3 contextually relevant next questions
  - RF-004: lineage — {tool, sql, tables, execution_time_ms, turn_id}
  - RF-005: confidence_score — blends query execution confidence + data completeness

Chart selection logic:
  Trend intent         → line/area
  Comparative intent   → bar
  Aggregation (single) → kpi_card
  Aggregation (multi)  → donut or bar
  Lookup               → table
  default              → table
"""

from __future__ import annotations

import json
from typing import Any

from app.agents.base import BaseAgent
from app.agents.state import AgentState

_NARRATIVE_SYSTEM = """\
You are an enterprise analytics assistant answering a business question from a SQL
result. Write the answer in Markdown with this structure:

1. A direct one- to two-sentence answer stating the headline figure(s), using the
   actual numbers and units from the data.
2. A "**Key insights**" section with 2–4 short bullet points highlighting what
   matters: the largest/smallest values, notable gaps or concentrations,
   comparisons between rows, trends, or anything surprising. Every bullet must
   cite specific numbers from the data.
3. (Optional) one short closing sentence of business interpretation or a caveat
   (e.g. the data only covers part of a period).

Rules:
- Use ONLY numbers present in the result — never invent, round away meaning, or
  extrapolate. Add currency/percent signs where the data implies them.
- Do NOT mention SQL, tables, columns, or other technical details.
- Be concise and direct — no preamble like "Based on the data". Write for a busy
  executive.
- If the result is empty, say so plainly and suggest a likely reason (no
  transactions in range, filters too narrow); omit the insights section.
"""

_FOLLOWUP_SYSTEM = """\
You are an analytics assistant. Given a question that was just answered, suggest 3 natural
follow-up questions a business analyst might ask next. Return ONLY a JSON array of strings.

Example: ["What drove the increase in Q3?", "How does this compare to last year?", "Which region performed best?"]
"""

_MAX_ROWS_FOR_LLM = 50  # truncate before sending to Claude
_MAX_COLS_FOR_LLM = 10  # too many columns overwhelm the prompt


class ResponseFormatterAgent(BaseAgent):
    name = "response_formatter"

    async def _run(self, state: AgentState) -> dict[str, Any]:
        result = state.get("query_result") or {}
        rows: list[dict] = result.get("rows", [])
        columns: list[str] = result.get("columns", [])
        row_count: int = result.get("row_count", 0)
        truncated: bool = result.get("truncated", False)

        question = state["question"]
        intent = state.get("intent", "Aggregation")
        tool = state.get("selected_tool") or {}

        # ── 1. Determine chart hint ──────────────────────────────────────────
        chart_hint = _choose_chart(intent, rows, columns)

        # ── 2. Generate narrative answer ─────────────────────────────────────
        answer_text = await self._generate_narrative(
            question, rows, columns, row_count, truncated
        )

        # ── 3. Anomaly scan on first numeric column ───────────────────────────
        anomalies: list[dict] = []
        if rows and columns:
            try:
                from app.services.analytics.anomaly import scan_column_for_anomalies
                for col in columns:
                    if any(isinstance(r.get(col), (int, float)) for r in rows[:5]):
                        anomalies = scan_column_for_anomalies(rows, col)
                        break
            except Exception:
                pass

        # ── 4. Structured answer_data for UI ─────────────────────────────────
        answer_data = {
            "chart_hint": chart_hint,
            "columns": columns,
            "rows": rows[:200],  # UI renders max 200 rows
            "row_count": row_count,
            "truncated": truncated,
            "summary": _compute_summary(rows, columns),
            "anomalies": anomalies,
        }

        # ── 5. Follow-up questions ────────────────────────────────────────────
        follow_ups = await self._generate_follow_ups(question)

        # ── 5. Lineage + reasoning trace ──────────────────────────────────────
        existing_lineage = state.get("lineage") or {}
        domain = state.get("detected_domain")
        is_text_to_sql = (
            bool(existing_lineage.get("text_to_sql"))
            or tool.get("name") == "ad_hoc_text_to_sql"
        )

        reasoning_steps = _build_reasoning(
            intent=intent,
            domain=domain,
            intent_reasoning=state.get("reasoning"),
            is_text_to_sql=is_text_to_sql,
            tool_name=tool.get("name"),
            tables_used=existing_lineage.get("tables_used"),
            row_count=row_count,
            execution_ms=state.get("execution_time_ms"),
        )

        lineage = {
            **existing_lineage,
            "tool_id": tool.get("tool_id"),
            "tool_name": tool.get("name"),
            "sql": state.get("sql_query"),
            "domain": tool.get("domain"),
            "category": tool.get("category"),
            "candidate_tools": state.get("candidate_tools", []),
            "entity_ids": [str(e) for e in (state.get("entity_ids") or [])],
            "execution_time_ms": state.get("execution_time_ms"),
            "turn_id": str(state.get("turn_id", "")),
            "intent": intent,
            "intent_reasoning": state.get("reasoning"),
            "reasoning": reasoning_steps,
        }

        # ── 6. Confidence score ───────────────────────────────────────────────
        classification_confidence = state.get("confidence") or 0.5
        data_confidence = _data_confidence(rows, row_count)
        confidence_score = round(
            0.5 * classification_confidence + 0.5 * data_confidence, 3
        )

        self._log.info(
            "response_formatter.done",
            chart_hint=chart_hint,
            row_count=row_count,
            confidence_score=confidence_score,
        )

        return {
            "answer_text": answer_text,
            "answer_data": answer_data,
            "chart_hint": chart_hint,
            "follow_up_questions": follow_ups,
            "lineage": lineage,
            "confidence_score": confidence_score,
        }

    async def _generate_narrative(
        self,
        question: str,
        rows: list[dict],
        columns: list[str],
        row_count: int,
        truncated: bool,
    ) -> str:
        if not rows:
            return (
                "No data was found matching your query. "
                "This may indicate that the specified date range has no transactions, "
                "or the filter criteria returned an empty result set."
            )

        # Trim for prompt
        sample_rows = rows[:_MAX_ROWS_FOR_LLM]
        sample_cols = columns[:_MAX_COLS_FOR_LLM]
        sample = [
            {c: r.get(c) for c in sample_cols}
            for r in sample_rows
        ]

        note = f"\n(Showing {_MAX_ROWS_FOR_LLM} of {row_count} rows)" if row_count > _MAX_ROWS_FOR_LLM else ""
        truncation_note = " Results were truncated at 1000 rows." if truncated else ""

        user_msg = (
            f"Question: {question}\n"
            f"Result ({row_count} rows total{truncation_note}):\n"
            f"{json.dumps(sample, default=str)}{note}"
        )

        try:
            return await self._call_llm(
                system=_NARRATIVE_SYSTEM,
                user=user_msg,
                max_tokens=512,
            )
        except Exception as exc:
            self._log.warning("response_formatter.narrative_fail", exc=str(exc))
            return f"Query returned {row_count} row(s). {truncation_note}"

    async def _generate_follow_ups(self, question: str) -> list[str]:
        try:
            raw = await self._call_llm(
                system=_FOLLOWUP_SYSTEM,
                user=f"Question just answered: {question}",
                max_tokens=256,
            )
            cleaned = raw.strip()
            if cleaned.startswith("["):
                parsed = json.loads(cleaned)
                if isinstance(parsed, list):
                    return [str(q) for q in parsed[:3]]
        except Exception:
            pass
        return [
            "Can you break this down by period?",
            "Which items are driving this result?",
            "How does this compare to the previous period?",
        ]


# ── Pure helpers ──────────────────────────────────────────────────────────────

def _build_reasoning(
    *,
    intent: str,
    domain: str | None,
    intent_reasoning: str | None,
    is_text_to_sql: bool,
    tool_name: str | None,
    tables_used: list[str] | None,
    row_count: int,
    execution_ms: int | None,
) -> list[str]:
    """Human-readable trace of how the answer was produced, for the UI's
    reasoning panel. Each entry is one short step."""
    steps: list[str] = []

    line = f"Interpreted your question as a **{intent}** request"
    if domain:
        line += f" in the **{domain}** domain"
    steps.append(line + ".")

    if intent_reasoning:
        steps.append(intent_reasoning)

    if is_text_to_sql:
        steps.append(
            "No pre-built tool matched, so I generated a SQL query directly from "
            "your connected schema."
        )
    elif tool_name:
        steps.append(f"Selected the **{tool_name}** analysis to answer it.")

    if tables_used:
        steps.append(f"Queried: {', '.join(tables_used)}.")

    ret = f"Returned {row_count} row(s)"
    if execution_ms is not None:
        ret += f" in {execution_ms} ms"
    steps.append(ret + ".")
    return steps


def _choose_chart(intent: str, rows: list[dict], columns: list[str]) -> str:
    """Heuristic chart hint from intent + result shape."""
    if intent == "Trend":
        return "line"
    if intent == "Comparative":
        return "bar"
    if intent == "Lookup":
        return "table"
    if intent in ("Aggregation", "RCA", "Hybrid"):
        if len(rows) == 1 and len(columns) <= 2:
            return "kpi_card"
        if len(rows) <= 6:
            return "donut"
        return "bar"
    return "table"


def _compute_summary(rows: list[dict], columns: list[str]) -> dict[str, Any]:
    """Extract lightweight summary stats for single-column numeric results."""
    if not rows or not columns:
        return {}
    # Try first numeric column
    for col in columns:
        vals = []
        for row in rows:
            v = row.get(col)
            if isinstance(v, (int, float)):
                vals.append(float(v))
        if vals:
            return {
                "column": col,
                "count": len(vals),
                "sum": round(sum(vals), 2),
                "min": round(min(vals), 2),
                "max": round(max(vals), 2),
                "avg": round(sum(vals) / len(vals), 2),
            }
    return {}


def _data_confidence(rows: list[dict], row_count: int) -> float:
    """Estimate data quality: empty = 0.2, 1+ rows with data = higher."""
    if row_count == 0:
        return 0.2
    # Non-null ratio in first row
    if rows:
        first = rows[0]
        non_null = sum(1 for v in first.values() if v is not None)
        total = len(first) or 1
        return 0.6 + 0.4 * (non_null / total)
    return 0.6
