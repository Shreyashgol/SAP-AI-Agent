"""
Sprint 6 unit tests — agent pipeline components.

Coverage:
  - DML guard (_check_dml)
  - Row-limit injection (_inject_row_limit)
  - Required param check (_check_required_params)
  - Param substitution (_substitute_params)
  - Chart hint selection (_choose_chart)
  - Data confidence scoring (_data_confidence)
  - Summary computation (_compute_summary)
  - Response formatter follow-up fallback
  - BaseAgent JSON extraction (inherited)
  - Supervisor routing functions
"""

import uuid
import pytest

from app.agents.sql_executor import (
    _check_dml,
    _check_required_params,
    _inject_row_limit,
    _substitute_params,
)
from app.agents.response_formatter import (
    _choose_chart,
    _compute_summary,
    _data_confidence,
)
from app.agents.supervisor import (
    _route_after_intent,
    _route_after_planner,
    _route_after_executor,
)
from app.agents.base import BaseAgent


# ── DML guard ─────────────────────────────────────────────────────────────────

class TestCheckDml:
    def test_allows_plain_select(self):
        assert _check_dml("SELECT * FROM invoices") is None

    def test_allows_select_with_comments(self):
        assert _check_dml("-- get invoices\nSELECT id FROM invoices") is None

    def test_blocks_insert(self):
        assert _check_dml("INSERT INTO t VALUES (1)") is not None

    def test_blocks_update(self):
        assert _check_dml("UPDATE t SET col=1") is not None

    def test_blocks_delete(self):
        assert _check_dml("DELETE FROM t WHERE 1=1") is not None

    def test_blocks_drop(self):
        assert _check_dml("DROP TABLE users") is not None

    def test_blocks_truncate(self):
        assert _check_dml("TRUNCATE TABLE logs") is not None

    def test_blocks_exec(self):
        assert _check_dml("EXEC sp_helpdb") is not None

    def test_blocks_merge(self):
        assert _check_dml("MERGE INTO t USING s ON t.id=s.id") is not None

    def test_blocks_non_select(self):
        assert _check_dml("WITH cte AS (SELECT 1) UPDATE t SET x=1") is not None

    def test_case_insensitive_block(self):
        assert _check_dml("insert into t values (1)") is not None

    def test_subquery_select_ok(self):
        sql = "SELECT * FROM (SELECT id FROM t WHERE active=1) sub"
        assert _check_dml(sql) is None


# ── Row limit injection ────────────────────────────────────────────────────────

class TestInjectRowLimit:
    def test_injects_top_when_missing(self):
        sql = "SELECT * FROM invoices"
        result = _inject_row_limit(sql, 1000)
        assert "TOP 1000" in result
        assert result.upper().startswith("SELECT TOP 1000")

    def test_does_not_double_inject_top_n(self):
        sql = "SELECT TOP 500 * FROM invoices"
        result = _inject_row_limit(sql, 1000)
        assert result.count("TOP") == 1
        assert "500" in result

    def test_does_not_inject_when_limit_param(self):
        sql = "SELECT TOP :limit id FROM t"
        result = _inject_row_limit(sql, 1000)
        assert "TOP 1000" not in result

    def test_case_insensitive_detection(self):
        sql = "select top 200 id from t"
        result = _inject_row_limit(sql, 1000)
        assert "TOP 1000" not in result

    def test_limit_clause_not_injected(self):
        sql = "SELECT id FROM t LIMIT 100"
        result = _inject_row_limit(sql, 1000)
        assert "TOP 1000" not in result


# ── Required params check ─────────────────────────────────────────────────────

class TestCheckRequiredParams:
    def test_all_present(self):
        schema = [{"name": "start_date", "required": True, "type": "string"}]
        params = {"start_date": "2024-01-01"}
        assert _check_required_params(schema, params) == []

    def test_missing_required(self):
        schema = [{"name": "start_date", "required": True, "type": "string"}]
        params = {}
        missing = _check_required_params(schema, params)
        assert "start_date" in missing

    def test_optional_not_flagged(self):
        schema = [{"name": "limit", "required": False, "type": "integer"}]
        params = {}
        assert _check_required_params(schema, params) == []

    def test_none_value_flagged_for_required(self):
        schema = [{"name": "end_date", "required": True, "type": "string"}]
        params = {"end_date": None}
        missing = _check_required_params(schema, params)
        assert "end_date" in missing

    def test_empty_schema(self):
        assert _check_required_params([], {}) == []


# ── Param substitution ────────────────────────────────────────────────────────

class TestSubstituteParams:
    def test_string_substitution(self):
        sql = "SELECT * FROM t WHERE name = :name"
        result = _substitute_params(sql, {"name": "Acme"})
        assert "'Acme'" in result
        assert ":name" not in result

    def test_integer_substitution(self):
        sql = "SELECT TOP :limit id FROM t"
        result = _substitute_params(sql, {"limit": 10})
        assert "10" in result
        assert ":limit" not in result

    def test_none_substituted_as_null(self):
        sql = "SELECT * FROM t WHERE val = :val"
        result = _substitute_params(sql, {"val": None})
        assert "NULL" in result

    def test_sql_injection_escaped(self):
        sql = "SELECT * FROM t WHERE name = :name"
        result = _substitute_params(sql, {"name": "O'Brien"})
        assert "O''Brien" in result

    def test_multiple_params(self):
        sql = "SELECT * FROM t WHERE a=:a AND b=:b"
        result = _substitute_params(sql, {"a": "x", "b": "y"})
        assert "'x'" in result
        assert "'y'" in result

    def test_boolean_true(self):
        sql = "SELECT * FROM t WHERE active=:active"
        result = _substitute_params(sql, {"active": True})
        assert "=1" in result.replace(" ", "")

    def test_boolean_false(self):
        sql = "SELECT * FROM t WHERE active=:active"
        result = _substitute_params(sql, {"active": False})
        assert "=0" in result.replace(" ", "")


# ── Chart hint selection ──────────────────────────────────────────────────────

class TestChooseChart:
    def test_trend_intent_returns_line(self):
        assert _choose_chart("Trend", [], []) == "line"

    def test_comparative_returns_bar(self):
        assert _choose_chart("Comparative", [], []) == "bar"

    def test_lookup_returns_table(self):
        assert _choose_chart("Lookup", [], []) == "table"

    def test_aggregation_single_row_returns_kpi_card(self):
        rows = [{"total": 12345.0}]
        cols = ["total"]
        assert _choose_chart("Aggregation", rows, cols) == "kpi_card"

    def test_aggregation_few_rows_returns_donut(self):
        rows = [{"cat": "A", "val": 1}, {"cat": "B", "val": 2}]
        cols = ["cat", "val"]
        assert _choose_chart("Aggregation", rows, cols) == "donut"

    def test_aggregation_many_rows_returns_bar(self):
        rows = [{"cat": str(i), "val": i} for i in range(10)]
        cols = ["cat", "val"]
        assert _choose_chart("Aggregation", rows, cols) == "bar"

    def test_unknown_intent_returns_table(self):
        assert _choose_chart("Unknown", [], []) == "table"


# ── Data confidence ───────────────────────────────────────────────────────────

class TestDataConfidence:
    def test_empty_rows_low_confidence(self):
        assert _data_confidence([], 0) == pytest.approx(0.2)

    def test_non_empty_rows_above_threshold(self):
        assert _data_confidence([{"col": "val"}], 1) > 0.6

    def test_all_non_null_row_max_confidence(self):
        row = {"a": 1, "b": 2, "c": 3}
        score = _data_confidence([row], 1)
        assert score == pytest.approx(0.6 + 0.4, rel=1e-3)

    def test_half_null_row_reduces_confidence(self):
        row = {"a": 1, "b": None}
        score = _data_confidence([row], 1)
        assert score == pytest.approx(0.6 + 0.4 * 0.5, rel=1e-3)


# ── Summary computation ───────────────────────────────────────────────────────

class TestComputeSummary:
    def test_empty_returns_empty(self):
        assert _compute_summary([], []) == {}

    def test_numeric_column_produces_stats(self):
        rows = [{"amount": 10.0}, {"amount": 20.0}, {"amount": 30.0}]
        summary = _compute_summary(rows, ["amount"])
        assert summary["column"] == "amount"
        assert summary["sum"] == pytest.approx(60.0)
        assert summary["min"] == pytest.approx(10.0)
        assert summary["max"] == pytest.approx(30.0)
        assert summary["avg"] == pytest.approx(20.0)

    def test_string_column_skipped(self):
        rows = [{"name": "A"}, {"name": "B"}]
        assert _compute_summary(rows, ["name"]) == {}

    def test_mixed_picks_first_numeric(self):
        rows = [{"label": "X", "value": 5.0}]
        summary = _compute_summary(rows, ["label", "value"])
        assert summary["column"] == "value"


# ── Supervisor routing ────────────────────────────────────────────────────────

def _state(**kwargs):
    """Minimal AgentState-like dict for routing tests."""
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
    }
    base.update(kwargs)
    return base


class TestSupervisorRouting:
    def test_data_intents_go_to_query_planner(self):
        for intent in ("Aggregation", "Trend", "Comparative", "RCA", "Lookup", "Hybrid"):
            state = _state(intent=intent)
            assert _route_after_intent(state) == "query_planner"

    def test_document_intent_goes_to_document_rag(self):
        state = _state(intent="Document")
        assert _route_after_intent(state) == "document_rag"

    def test_web_intent_goes_to_web_search(self):
        state = _state(intent="Web")
        assert _route_after_intent(state) == "web_search"

    def test_error_after_intent_goes_to_error_handler(self):
        state = _state(error="something went wrong")
        assert _route_after_intent(state) == "error_handler"

    def test_planner_with_tool_goes_to_executor(self):
        state = _state(selected_tool={"name": "ar_total"})
        assert _route_after_planner(state) == "sql_executor"

    def test_planner_no_tool_goes_to_error(self):
        state = _state(selected_tool=None)
        assert _route_after_planner(state) == "error_handler"

    def test_planner_error_goes_to_error_handler(self):
        state = _state(error="no tools found", selected_tool=None)
        assert _route_after_planner(state) == "error_handler"

    def test_executor_success_goes_to_formatter(self):
        state = _state(query_result={"rows": [], "columns": [], "row_count": 0})
        assert _route_after_executor(state) == "response_formatter"

    def test_executor_error_goes_to_error_handler(self):
        state = _state(error="query failed")
        assert _route_after_executor(state) == "error_handler"


# ── BaseAgent JSON extraction ─────────────────────────────────────────────────

class TestBaseAgentJsonExtraction:
    def test_plain_json(self):
        result = BaseAgent._extract_json('{"intent": "Aggregation"}')
        assert result == {"intent": "Aggregation"}

    def test_markdown_fenced_json(self):
        text = "```json\n{\"intent\": \"Trend\"}\n```"
        result = BaseAgent._extract_json(text)
        assert result == {"intent": "Trend"}

    def test_json_embedded_in_text(self):
        text = 'Here is the result: {"key": "value"} done.'
        result = BaseAgent._extract_json(text)
        assert result == {"key": "value"}

    def test_invalid_json_returns_none(self):
        assert BaseAgent._extract_json("not json at all") is None

    def test_empty_returns_none(self):
        assert BaseAgent._extract_json("") is None
