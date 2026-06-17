"""
Trend Agent — post-processes time-series SQL results into period-over-period analytics.

Spec: AG-010, TR-001, TR-002, TR-003
  - TR-001: Receives query_result from sql_executor (time-bucketed rows expected)
  - TR-002: Computes period-over-period deltas, CAGR, and directional trend
  - TR-003: Selects line/area chart hint; structures data for sparkline rendering
  - TR-004: Asks Claude to narrate the trend in 2-3 business sentences

Runs after sql_executor for Trend intent ONLY. response_formatter is skipped.

Expected input shape (from time-series tools):
  rows with at least one date/period column and one numeric column.
  Examples:
    [{period: "2024-01", revenue: 150000}, {period: "2024-02", revenue: 162000}, ...]
    [{DocDate: "2024-01-01", DocTotal: 8500}, ...]

Output:
  - trend_data: {series: [{label, value}], deltas: [{label, delta_pct}], direction}
  - chart_hint: "line" (default) or "area" for cumulative metrics
  - answer_text: Claude narrative
  - confidence_score: based on data completeness + direction clarity
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.agents.base import BaseAgent
from app.agents.state import AgentState

_TREND_SYSTEM = """\
You are an enterprise analytics expert. Given time-series business data with
period-over-period changes, write a 2-3 sentence executive summary describing:
1. The overall trend direction (growing/declining/stable) and magnitude
2. The most notable change between any two adjacent periods
3. Any pattern (seasonal, accelerating, decelerating) if visible

Be precise — use actual numbers and percentages from the data.
Do not use vague language. Write for a CFO or business executive.
Output: plain prose only, no bullet points, no JSON.
"""

# Column name patterns that suggest a date/period dimension
_DATE_PATTERNS = re.compile(
    r"\b(date|period|month|week|year|quarter|day|time|doc_date|docdate)\b",
    re.IGNORECASE,
)

# Column name patterns that suggest a numeric metric
_METRIC_PATTERNS = re.compile(
    r"\b(total|amount|revenue|sales|value|count|qty|quantity|"
    r"sum|profit|cost|spend|balance|volume|margin|rate|score)\b",
    re.IGNORECASE,
)


class TrendAgent(BaseAgent):
    name = "trend_agent"

    async def _run(self, state: AgentState) -> dict[str, Any]:
        result = state.get("query_result") or {}
        rows: list[dict] = result.get("rows", [])
        columns: list[str] = result.get("columns", [])
        question = state.get("enriched_question") or state["question"]

        if not rows:
            return {
                "answer_text": (
                    "No time-series data was returned for this period. "
                    "The selected date range may have no transactions."
                ),
                "answer_data": {"type": "trend", "series": [], "deltas": []},
                "chart_hint": "line",
                "follow_up_questions": ["Can you try a wider date range?"],
                "confidence_score": 0.1,
                "lineage": state.get("lineage"),
            }

        # Identify period and metric columns. Date-like columns (Year, Month,
        # DocDate, …) are excluded from metric candidates so a column such as
        # "SalesMonth" is never mistaken for the metric just because it contains
        # "sales". When both a year and a month column exist, the period label
        # is the composite "YYYY-MM" so each month is a distinct point.
        date_cols = [c for c in columns if _DATE_PATTERNS.search(_normalize(c))]
        metric_candidates = [c for c in columns if c not in date_cols] or columns
        metric_col = _pick_column(metric_candidates, _METRIC_PATTERNS) or metric_candidates[0]

        year_col = _find(date_cols, r"year")
        month_col = _find(date_cols, r"month")
        period_col = date_cols[0] if date_cols else columns[0]

        # Build ordered series
        series = _extract_series(rows, period_col, metric_col, year_col, month_col)

        if not series:
            return {
                "answer_text": "Could not extract a numeric time series from the query result.",
                "answer_data": {"type": "trend", "series": [], "deltas": []},
                "chart_hint": "line",
                "follow_up_questions": [],
                "confidence_score": 0.2,
                "lineage": state.get("lineage"),
            }

        # Compute deltas and statistics
        deltas = _compute_deltas(series)
        direction = _trend_direction(series)
        cagr = _compute_cagr(series)

        trend_data = {
            "type": "trend",
            "period_column": period_col,
            "metric_column": metric_col,
            "series": series,
            "deltas": deltas,
            "direction": direction,
            "cagr_pct": cagr,
            "periods": len(series),
        }

        # Narrative
        context = (
            f"Question: {question}\n"
            f"Metric: {metric_col} over {len(series)} periods\n"
            f"Direction: {direction}\n"
            f"CAGR: {cagr:.1f}%\n"
            f"Data (label → value): {json.dumps(series[:20], default=str)}"
        )
        answer_text = await self._call_llm(
            system=_TREND_SYSTEM,
            user=context,
            model=self._default_model,
            max_tokens=512,
        )

        chart_hint = "area" if _is_cumulative_metric(metric_col) else "line"

        # Confidence: more periods = more confidence; clear direction adds confidence
        direction_bonus = 0.1 if direction in ("up", "down") else 0.0
        data_conf = min(0.9, 0.4 + 0.05 * len(series)) + direction_bonus
        confidence = round(data_conf, 3)

        follow_ups = [
            f"What drove the changes in {metric_col}?",
            "How does this compare to the same period last year?",
            f"Which segments are contributing most to the {direction} trend?",
        ]

        self._log.info(
            "trend_agent.done",
            periods=len(series),
            direction=direction,
            cagr=round(cagr, 2),
        )

        return {
            "answer_text": answer_text,
            "answer_data": trend_data,
            "chart_hint": chart_hint,
            "follow_up_questions": follow_ups,
            "confidence_score": confidence,
            "lineage": state.get("lineage"),
        }


# ── Pure helpers ──────────────────────────────────────────────────────────────

def _normalize(col: str) -> str:
    """Split CamelCase/PascalCase and snake_case into space-separated words so
    `\\bword\\b` patterns match SAP-style columns ('SalesYear' → 'sales year')."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", col)
    return spaced.replace("_", " ").lower()


def _pick_column(columns: list[str], pattern: re.Pattern) -> str | None:
    for col in columns:
        if pattern.search(_normalize(col)):
            return col
    return None


def _find(columns: list[str], word: str) -> str | None:
    rx = re.compile(word, re.IGNORECASE)
    return next((c for c in columns if rx.search(_normalize(c))), None)


def _period_label(row: dict, period_col: str, year_col: str | None, month_col: str | None) -> str:
    """Composite 'YYYY-MM' when both year and month columns exist, else the raw period."""
    if year_col and month_col:
        try:
            return f"{int(row[year_col])}-{int(row[month_col]):02d}"
        except (TypeError, ValueError, KeyError):
            pass
    return str(row.get(period_col, ""))


def _extract_series(
    rows: list[dict],
    period_col: str,
    metric_col: str,
    year_col: str | None = None,
    month_col: str | None = None,
) -> list[dict[str, Any]]:
    """Return [{label, value}] sorted by label (assumes ISO-sortable labels)."""
    series = []
    for row in rows:
        label = _period_label(row, period_col, year_col, month_col)
        val = row.get(metric_col)
        try:
            value = float(val)  # type: ignore[arg-type]
            series.append({"label": label, "value": round(value, 4)})
        except (TypeError, ValueError):
            pass
    series.sort(key=lambda x: x["label"])
    return series


def _compute_deltas(series: list[dict]) -> list[dict]:
    """Return [{label, delta_pct}] for each consecutive pair."""
    if len(series) < 2:
        return []
    deltas = []
    for i in range(1, len(series)):
        prev = series[i - 1]["value"]
        curr = series[i]["value"]
        if prev != 0:
            pct = round((curr - prev) / abs(prev) * 100, 2)
        else:
            pct = None
        deltas.append({
            "label": series[i]["label"],
            "delta_pct": pct,
            "delta_abs": round(curr - prev, 4),
        })
    return deltas


def _trend_direction(series: list[dict]) -> str:
    """Simple OLS slope sign to determine trend direction."""
    if len(series) < 2:
        return "flat"
    values = [s["value"] for s in series]
    n = len(values)
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(values) / n
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values))
    den = sum((x - x_mean) ** 2 for x in xs)
    if den == 0:
        return "flat"
    slope = num / den
    # Slope relative to mean value
    rel = slope / abs(y_mean) if y_mean != 0 else slope
    if rel > 0.01:
        return "up"
    if rel < -0.01:
        return "down"
    return "flat"


def _compute_cagr(series: list[dict]) -> float:
    """Compound annual growth rate approximation over the series."""
    if len(series) < 2:
        return 0.0
    first = series[0]["value"]
    last = series[-1]["value"]
    periods = len(series) - 1
    if first <= 0 or last <= 0 or periods == 0:
        return 0.0
    try:
        return ((last / first) ** (1.0 / periods) - 1) * 100
    except (ValueError, ZeroDivisionError):
        return 0.0


def _is_cumulative_metric(col: str) -> bool:
    """Area chart suits cumulative/stock metrics; line suits flow metrics."""
    cumulative = re.compile(
        r"\b(balance|stock|inventory|outstanding|cumulative|total stock|on hand)\b",
        re.IGNORECASE,
    )
    return bool(cumulative.search(col.replace("_", " ")))
