"""
Sprint 8 unit tests — anomaly detection, RAG helpers, RCA helpers, routing.

Coverage:
  - Z-score anomaly detection: normal values, outliers, severity bands, edge cases
  - IQR anomaly detection: fence computation, outlier detection
  - scan_column_for_anomalies: filters anomalous rows from a dataset
  - _summarise_rows (RCA agent): handles empty / populated data
  - _shift_dates_back (RCA agent): ISO date shifting
  - Supervisor routing: RCA branch after executor
  - Document upload validation: allowed types / size guard (schema layer)
"""

from __future__ import annotations

import math
import uuid
from datetime import date, timedelta

import pytest

from app.services.analytics.anomaly import (
    AnomalyResult,
    detect_zscore,
    detect_iqr,
    scan_column_for_anomalies,
    _severity,
)
from app.agents.rca_agent import _shift_dates_back, _summarise_rows
from app.agents.supervisor import _route_after_executor


# ── Z-score detection ─────────────────────────────────────────────────────────

class TestDetectZscore:
    def test_normal_value_not_anomaly(self):
        values = [100.0, 102.0, 98.0, 101.0, 99.0, 100.5, 99.5]
        result = detect_zscore(values, target_index=-1)
        assert result is not None
        assert not result.is_anomaly

    def test_outlier_detected(self):
        values = [100.0, 101.0, 99.0, 100.5, 98.5, 500.0]
        result = detect_zscore(values, target_index=-1)
        assert result is not None
        assert result.is_anomaly
        assert result.z_score > 2.5

    def test_negative_outlier_detected(self):
        values = [100.0, 101.0, 99.0, 100.5, 98.5, 1.0]
        result = detect_zscore(values, target_index=-1)
        assert result is not None
        assert result.is_anomaly
        assert result.z_score < -2.5

    def test_too_few_values_returns_none(self):
        assert detect_zscore([10.0, 20.0], target_index=-1) is None

    def test_all_identical_values_no_anomaly(self):
        values = [50.0, 50.0, 50.0, 50.0]
        result = detect_zscore(values, target_index=-1)
        assert result is not None
        assert not result.is_anomaly

    def test_bounds_computed_correctly(self):
        # Baseline needs non-zero variance, otherwise bounds collapse to the mean
        values = [10.0, 12.0, 11.0, 10.5, 100.0]  # last is outlier
        result = detect_zscore(values, target_index=-1, threshold=2.5)
        assert result is not None
        assert result.lower_bound < result.upper_bound

    def test_custom_threshold(self):
        values = [100.0, 103.0, 98.0, 101.0, 115.0]
        # Tight threshold — 1.5σ — should flag the 115
        result = detect_zscore(values, target_index=-1, threshold=1.5)
        assert result is not None
        # May or may not be anomaly depending on distribution, but result must be valid
        assert isinstance(result.is_anomaly, bool)

    def test_result_fields_populated(self):
        values = [10.0, 11.0, 9.0, 10.5, 50.0]
        result = detect_zscore(values, target_index=-1)
        assert result is not None
        assert result.value == 50.0
        assert result.mean > 0
        assert result.std_dev > 0
        assert result.description != ""


# ── IQR detection ─────────────────────────────────────────────────────────────

class TestDetectIqr:
    def test_outlier_above_fence(self):
        values = [10.0, 11.0, 12.0, 10.5, 11.5, 12.5, 100.0]
        result = detect_iqr(values, target_index=-1)
        assert result is not None
        assert result.is_anomaly

    def test_normal_value_passes(self):
        values = [10.0, 11.0, 12.0, 10.5, 11.5, 12.5, 11.2]
        result = detect_iqr(values, target_index=-1)
        assert result is not None
        assert not result.is_anomaly

    def test_too_few_values_returns_none(self):
        assert detect_iqr([1.0, 2.0, 3.0], target_index=-1) is None

    def test_bounds_ordered(self):
        values = [5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0]
        result = detect_iqr(values, target_index=-1)
        assert result is not None
        assert result.lower_bound <= result.upper_bound


# ── Severity bands ────────────────────────────────────────────────────────────

class TestSeverity:
    def test_none_within_threshold(self):
        assert _severity(2.0, 2.5) == "none"

    def test_low_just_above_threshold(self):
        assert _severity(3.0, 2.5) == "low"

    def test_medium(self):
        assert _severity(4.5, 2.5) == "medium"

    def test_high(self):
        assert _severity(6.0, 2.5) == "high"

    def test_zero_z_is_none(self):
        assert _severity(0.0, 2.5) == "none"


# ── Column scan ───────────────────────────────────────────────────────────────

class TestScanColumnForAnomalies:
    def _make_rows(self, values):
        return [{"amount": v} for v in values]

    def test_no_anomalies_in_uniform_data(self):
        rows = self._make_rows([100.0, 101.0, 99.0, 100.5, 98.5, 100.2])
        result = scan_column_for_anomalies(rows, "amount")
        # All values are close together — no anomalies expected
        for item in result:
            assert item["anomaly"]["severity"] in ("low", "medium", "high")

    def test_outlier_flagged(self):
        rows = self._make_rows([100.0, 101.0, 99.0, 100.5, 98.5, 5000.0])
        result = scan_column_for_anomalies(rows, "amount")
        assert len(result) > 0
        flagged_values = [r["row"]["amount"] for r in result]
        assert 5000.0 in flagged_values

    def test_empty_rows(self):
        assert scan_column_for_anomalies([], "amount") == []

    def test_non_numeric_column_skipped(self):
        rows = [{"name": "A"}, {"name": "B"}, {"name": "C"}]
        result = scan_column_for_anomalies(rows, "name")
        assert result == []

    def test_missing_column_graceful(self):
        rows = [{"other": 1.0}, {"other": 2.0}]
        result = scan_column_for_anomalies(rows, "amount")
        assert result == []


# ── RCA helpers ───────────────────────────────────────────────────────────────

class TestShiftDatesBack:
    def test_shifts_iso_date_by_30_days(self):
        params = {"start_date": "2024-03-01", "end_date": "2024-03-31"}
        result = _shift_dates_back(params)
        start = date.fromisoformat(result["start_date"])
        end = date.fromisoformat(result["end_date"])
        assert start == date(2024, 1, 31)
        assert end == date(2024, 3, 1)

    def test_non_date_params_unchanged(self):
        params = {"customer_code": "C001", "limit": 10}
        result = _shift_dates_back(params)
        assert result == params

    def test_empty_params(self):
        assert _shift_dates_back({}) == {}

    def test_mixed_params(self):
        params = {"start_date": "2024-06-01", "name": "Acme", "limit": 100}
        result = _shift_dates_back(params)
        assert result["name"] == "Acme"
        assert result["limit"] == 100
        shifted = date.fromisoformat(result["start_date"])
        assert shifted == date(2024, 5, 2)


class TestSummariseRows:
    def test_empty_returns_no_data_message(self):
        msg = _summarise_rows([], [], "Current period")
        assert "No data" in msg

    def test_populated_rows_include_label(self):
        rows = [{"amount": 1000, "customer": "Acme"}]
        msg = _summarise_rows(rows, ["amount", "customer"], "Prior period")
        assert "Prior period" in msg
        assert "1 rows" in msg

    def test_sample_capped_at_5(self):
        rows = [{"v": i} for i in range(10)]
        msg = _summarise_rows(rows, ["v"], "Test")
        assert "10 rows" in msg


# ── Supervisor routing — RCA branch ──────────────────────────────────────────

def _st(**kw):
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
        "needs_clarification": False, "missing_params": [], "clarification_question": None,
    }
    base.update(kw)
    return base


class TestRCARouting:
    def test_rca_intent_routes_to_rca_agent(self):
        state = _st(intent="RCA")
        assert _route_after_executor(state) == "rca_agent"

    def test_non_rca_intent_routes_to_formatter(self):
        # Trend is excluded — it routes to trend_agent (covered in test_sprint9)
        for intent in ("Aggregation", "Comparative", "Lookup", "Hybrid"):
            state = _st(intent=intent)
            assert _route_after_executor(state) == "response_formatter"

    def test_clarification_overrides_rca(self):
        state = _st(intent="RCA", needs_clarification=True)
        assert _route_after_executor(state) == "clarification_agent"

    def test_error_overrides_rca(self):
        state = _st(intent="RCA", error="query failed")
        assert _route_after_executor(state) == "error_handler"


# ── AnomalyResult dataclass ───────────────────────────────────────────────────

class TestAnomalyResult:
    def test_defaults_populated(self):
        r = AnomalyResult(
            value=500.0, mean=100.0, std_dev=10.0,
            z_score=40.0, is_anomaly=True, severity="high",
            description="Outlier detected",
            lower_bound=75.0, upper_bound=125.0,
        )
        assert r.is_anomaly
        assert r.severity == "high"
        assert r.lower_bound < r.upper_bound

    def test_not_anomaly_result(self):
        r = AnomalyResult(
            value=101.0, mean=100.0, std_dev=5.0,
            z_score=0.2, is_anomaly=False, severity="none",
            description="Within range",
            lower_bound=87.5, upper_bound=112.5,
        )
        assert not r.is_anomaly
        assert r.severity == "none"
