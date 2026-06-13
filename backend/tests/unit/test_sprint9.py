"""
Sprint 9 unit tests — Trend agent helpers, Hybrid short-circuit,
query cache key generation, circuit breaker, export sanitisation.

Coverage:
  - _pick_column: date and metric pattern matching
  - _extract_series: label/value extraction, sorting, non-numeric skipping
  - _compute_deltas: percent and absolute deltas, zero-division guard
  - _trend_direction: OLS slope sign (up / down / flat)
  - _compute_cagr: compound growth rate, edge cases
  - _is_cumulative_metric: area vs line chart selection
  - query_cache._cache_key: determinism, tenant isolation, SQL normalisation
  - query_cache: intent bypass for RCA/Trend
  - export._sanitise_cell: formula injection prevention
  - export._sanitise_xlsx_cell: formula injection prevention
  - supervisor routing: Trend intent → trend_agent, Hybrid → hybrid_agent
"""

from __future__ import annotations

import hashlib
import json
import uuid

import pytest

from app.agents.trend_agent import (
    TrendAgent,
    _pick_column,
    _extract_series,
    _compute_deltas,
    _trend_direction,
    _compute_cagr,
    _is_cumulative_metric,
)
from app.agents.supervisor import _route_after_executor, _route_after_formatter
from app.api.v1.endpoints.export import _sanitise_cell, _sanitise_xlsx_cell
from app.services.cache.query_cache import _cache_key


# ── _pick_column ──────────────────────────────────────────────────────────────

class TestPickColumn:
    def test_picks_date_column(self):
        cols = ["customer", "DocDate", "amount"]
        from app.agents.trend_agent import _DATE_PATTERNS
        assert _pick_column(cols, _DATE_PATTERNS) == "DocDate"

    def test_picks_period_column(self):
        from app.agents.trend_agent import _DATE_PATTERNS
        assert _pick_column(["period", "value"], _DATE_PATTERNS) == "period"

    def test_picks_month_column(self):
        from app.agents.trend_agent import _DATE_PATTERNS
        assert _pick_column(["month", "sales"], _DATE_PATTERNS) == "month"

    def test_picks_metric_column(self):
        cols = ["period", "revenue", "customer_count"]
        from app.agents.trend_agent import _METRIC_PATTERNS
        assert _pick_column(cols, _METRIC_PATTERNS) == "revenue"

    def test_returns_none_when_no_match(self):
        from app.agents.trend_agent import _DATE_PATTERNS
        assert _pick_column(["foo", "bar"], _DATE_PATTERNS) is None

    def test_case_insensitive(self):
        from app.agents.trend_agent import _METRIC_PATTERNS
        assert _pick_column(["TOTAL_SALES"], _METRIC_PATTERNS) == "TOTAL_SALES"


# ── _extract_series ───────────────────────────────────────────────────────────

class TestExtractSeries:
    def test_basic_extraction(self):
        rows = [
            {"period": "2024-01", "revenue": 100.0},
            {"period": "2024-02", "revenue": 150.0},
        ]
        result = _extract_series(rows, "period", "revenue")
        assert len(result) == 2
        assert result[0]["label"] == "2024-01"
        assert result[0]["value"] == 100.0

    def test_sorted_by_label(self):
        rows = [
            {"period": "2024-03", "revenue": 300.0},
            {"period": "2024-01", "revenue": 100.0},
            {"period": "2024-02", "revenue": 200.0},
        ]
        result = _extract_series(rows, "period", "revenue")
        assert [r["label"] for r in result] == ["2024-01", "2024-02", "2024-03"]

    def test_non_numeric_values_skipped(self):
        rows = [
            {"period": "2024-01", "revenue": "N/A"},
            {"period": "2024-02", "revenue": 200.0},
        ]
        result = _extract_series(rows, "period", "revenue")
        assert len(result) == 1
        assert result[0]["label"] == "2024-02"

    def test_none_values_skipped(self):
        rows = [
            {"period": "2024-01", "revenue": None},
            {"period": "2024-02", "revenue": 200.0},
        ]
        result = _extract_series(rows, "period", "revenue")
        assert len(result) == 1

    def test_integer_values_coerced(self):
        rows = [{"month": "Jan", "count": 42}]
        result = _extract_series(rows, "month", "count")
        assert result[0]["value"] == 42.0

    def test_empty_rows(self):
        assert _extract_series([], "period", "revenue") == []


# ── _compute_deltas ───────────────────────────────────────────────────────────

class TestComputeDeltas:
    def test_basic_delta(self):
        series = [
            {"label": "Jan", "value": 100.0},
            {"label": "Feb", "value": 110.0},
        ]
        deltas = _compute_deltas(series)
        assert len(deltas) == 1
        assert deltas[0]["delta_pct"] == pytest.approx(10.0)
        assert deltas[0]["delta_abs"] == pytest.approx(10.0)

    def test_decline_delta(self):
        series = [
            {"label": "Jan", "value": 200.0},
            {"label": "Feb", "value": 100.0},
        ]
        deltas = _compute_deltas(series)
        assert deltas[0]["delta_pct"] == pytest.approx(-50.0)

    def test_zero_prev_returns_none_pct(self):
        series = [
            {"label": "Jan", "value": 0.0},
            {"label": "Feb", "value": 100.0},
        ]
        deltas = _compute_deltas(series)
        assert deltas[0]["delta_pct"] is None
        assert deltas[0]["delta_abs"] == pytest.approx(100.0)

    def test_single_element_returns_empty(self):
        assert _compute_deltas([{"label": "Jan", "value": 100.0}]) == []

    def test_multi_period_length(self):
        series = [{"label": str(i), "value": float(i * 10)} for i in range(5)]
        deltas = _compute_deltas(series)
        assert len(deltas) == 4


# ── _trend_direction ──────────────────────────────────────────────────────────

class TestTrendDirection:
    def test_upward_trend(self):
        series = [{"label": str(i), "value": float(i * 10 + 100)} for i in range(6)]
        assert _trend_direction(series) == "up"

    def test_downward_trend(self):
        series = [{"label": str(i), "value": float(100 - i * 10)} for i in range(6)]
        assert _trend_direction(series) == "down"

    def test_flat_trend(self):
        series = [{"label": str(i), "value": 100.0} for i in range(5)]
        assert _trend_direction(series) == "flat"

    def test_single_point_flat(self):
        assert _trend_direction([{"label": "a", "value": 10.0}]) == "flat"

    def test_two_equal_points_flat(self):
        series = [{"label": "a", "value": 50.0}, {"label": "b", "value": 50.0}]
        assert _trend_direction(series) == "flat"


# ── _compute_cagr ─────────────────────────────────────────────────────────────

class TestComputeCagr:
    def test_known_cagr(self):
        # 100 → 121 over 2 periods = 10% CAGR
        series = [
            {"label": "Y1", "value": 100.0},
            {"label": "Y2", "value": 110.0},
            {"label": "Y3", "value": 121.0},
        ]
        cagr = _compute_cagr(series)
        assert cagr == pytest.approx(10.0, abs=0.1)

    def test_single_period_returns_zero(self):
        assert _compute_cagr([{"label": "a", "value": 100.0}]) == 0.0

    def test_zero_first_value_returns_zero(self):
        series = [
            {"label": "a", "value": 0.0},
            {"label": "b", "value": 100.0},
        ]
        assert _compute_cagr(series) == 0.0

    def test_negative_values_returns_zero(self):
        series = [
            {"label": "a", "value": -10.0},
            {"label": "b", "value": 50.0},
        ]
        assert _compute_cagr(series) == 0.0


# ── _is_cumulative_metric ─────────────────────────────────────────────────────

class TestIsCumulativeMetric:
    def test_balance_is_cumulative(self):
        assert _is_cumulative_metric("balance") is True

    def test_stock_is_cumulative(self):
        assert _is_cumulative_metric("inventory_stock") is True

    def test_revenue_is_not_cumulative(self):
        assert _is_cumulative_metric("revenue") is False

    def test_sales_is_not_cumulative(self):
        assert _is_cumulative_metric("total_sales") is False

    def test_case_insensitive(self):
        assert _is_cumulative_metric("BALANCE") is True


# ── Query cache key ───────────────────────────────────────────────────────────

class TestCacheKey:
    def test_deterministic(self):
        key1 = _cache_key("t1", "c1", "SELECT 1", {})
        key2 = _cache_key("t1", "c1", "SELECT 1", {})
        assert key1 == key2

    def test_tenant_isolation(self):
        key1 = _cache_key("tenant_A", "conn1", "SELECT 1", {})
        key2 = _cache_key("tenant_B", "conn1", "SELECT 1", {})
        assert key1 != key2

    def test_sql_normalisation(self):
        # Different whitespace → same key
        key1 = _cache_key("t", "c", "SELECT  *  FROM  T1", {})
        key2 = _cache_key("t", "c", "SELECT * FROM T1", {})
        assert key1 == key2

    def test_params_affect_key(self):
        key1 = _cache_key("t", "c", "SELECT 1", {"start": "2024-01"})
        key2 = _cache_key("t", "c", "SELECT 1", {"start": "2024-02"})
        assert key1 != key2

    def test_key_prefix(self):
        key = _cache_key("t", "c", "SELECT 1", {})
        assert key.startswith("qcache:t:")

    def test_key_format(self):
        key = _cache_key("mytenant", "myconn", "SELECT 1", {})
        parts = key.split(":")
        assert parts[0] == "qcache"
        assert parts[1] == "mytenant"
        assert len(parts[2]) == 32  # 32-char hex digest


# ── Query cache intent bypass ─────────────────────────────────────────────────

class TestQueryCacheIntentBypass:
    """These are synchronous tests over the pure logic (no Redis connection)."""

    def test_rca_key_would_be_skipped(self):
        # Verify the _NO_CACHE_INTENTS set contains RCA and Trend
        from app.services.cache.query_cache import _NO_CACHE_INTENTS
        assert "RCA" in _NO_CACHE_INTENTS
        assert "Trend" in _NO_CACHE_INTENTS

    def test_aggregation_not_in_bypass(self):
        from app.services.cache.query_cache import _NO_CACHE_INTENTS
        assert "Aggregation" not in _NO_CACHE_INTENTS

    def test_hybrid_not_in_bypass(self):
        from app.services.cache.query_cache import _NO_CACHE_INTENTS
        assert "Hybrid" not in _NO_CACHE_INTENTS


# ── Export sanitisation ───────────────────────────────────────────────────────

class TestSanitiseCell:
    def test_normal_value_unchanged(self):
        assert _sanitise_cell("hello") == "hello"

    def test_numeric_unchanged(self):
        assert _sanitise_cell(42) == "42"

    def test_none_becomes_empty(self):
        assert _sanitise_cell(None) == ""

    def test_equals_prefix_escaped(self):
        result = _sanitise_cell("=SUM(A1:A10)")
        assert result.startswith("'")

    def test_plus_prefix_escaped(self):
        assert _sanitise_cell("+1234567890").startswith("'")

    def test_minus_prefix_escaped(self):
        assert _sanitise_cell("-DROP TABLE users").startswith("'")

    def test_at_prefix_escaped(self):
        assert _sanitise_cell("@SUM(B1)").startswith("'")

    def test_float_unchanged(self):
        assert _sanitise_cell(3.14) == "3.14"


class TestSanitiseXlsxCell:
    def test_normal_value_unchanged(self):
        assert _sanitise_xlsx_cell("Revenue") == "Revenue"

    def test_none_becomes_empty_string(self):
        assert _sanitise_xlsx_cell(None) == ""

    def test_formula_prefixed_with_space(self):
        result = _sanitise_xlsx_cell("=HYPERLINK()")
        assert result.startswith(" ")

    def test_numeric_returned_as_string(self):
        result = _sanitise_xlsx_cell(100)
        assert result == "100"


# ── Supervisor routing — Trend and Hybrid ────────────────────────────────────

def _mk_state(**kw):
    base = {
        "messages": [], "question": "q", "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(), "conversation_id": uuid.uuid4(),
        "turn_id": uuid.uuid4(), "connection_id": None,
        "intent": None, "detected_domain": None, "enriched_question": None,
        "confidence": None, "candidate_tools": [], "selected_tool": None,
        "resolved_params": {}, "join_path": None, "entity_ids": [],
        "sql_query": None, "query_result": None, "execution_time_ms": None,
        "answer_text": None, "answer_data": None, "chart_hint": None,
        "follow_up_questions": [], "lineage": None, "confidence_score": None,
        "error": None, "fallback_used": False, "agents_invoked": [],
        "needs_clarification": False, "missing_params": [],
        "clarification_question": None,
    }
    base.update(kw)
    return base


class TestTrendRouting:
    def test_trend_intent_routes_to_trend_agent(self):
        state = _mk_state(intent="Trend")
        assert _route_after_executor(state) == "trend_agent"

    def test_rca_still_routes_to_rca_agent(self):
        state = _mk_state(intent="RCA")
        assert _route_after_executor(state) == "rca_agent"

    def test_other_intents_route_to_formatter(self):
        for intent in ("Aggregation", "Lookup", "Comparative", "Hybrid"):
            state = _mk_state(intent=intent)
            assert _route_after_executor(state) == "response_formatter"

    def test_clarification_overrides_trend(self):
        state = _mk_state(intent="Trend", needs_clarification=True)
        assert _route_after_executor(state) == "clarification_agent"

    def test_error_overrides_trend(self):
        state = _mk_state(intent="Trend", error="executor failed")
        assert _route_after_executor(state) == "error_handler"


class TestHybridRouting:
    def test_hybrid_routes_to_hybrid_agent(self):
        from langgraph.graph import END
        state = _mk_state(intent="Hybrid")
        assert _route_after_formatter(state) == "hybrid_agent"

    def test_non_hybrid_routes_to_end(self):
        from langgraph.graph import END
        for intent in ("Aggregation", "Lookup", "Comparative", "Trend"):
            state = _mk_state(intent=intent)
            assert _route_after_formatter(state) == END

    def test_none_intent_routes_to_end(self):
        from langgraph.graph import END
        state = _mk_state(intent=None)
        assert _route_after_formatter(state) == END
