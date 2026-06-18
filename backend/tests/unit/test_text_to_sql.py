"""
Tests for the text-to-SQL runtime fallback.

Covers:
  - query_planner routes a no-tool result to the text_to_sql node (not an error).
  - _clean_sql strips fences/prose and isolates the SELECT.
  - text_to_sql routing into sql_executor / error_handler.
  - response_formatter._build_reasoning produces a readable trace.
"""

import pytest

from app.agents.text_to_sql import _clean_sql
from app.agents.supervisor import _route_after_planner, _route_after_text_to_sql
from app.agents.response_formatter import _build_reasoning


# ── Routing: no curated tool → text-to-SQL fallback ───────────────────────────

@pytest.mark.unit
def test_no_tool_routes_to_text_to_sql():
    state = {"error": None, "selected_tool": None, "use_text_to_sql": True}
    assert _route_after_planner(state) == "text_to_sql"


@pytest.mark.unit
def test_no_tool_without_flag_routes_to_error():
    state = {"error": None, "selected_tool": None}
    assert _route_after_planner(state) == "error_handler"


@pytest.mark.unit
def test_tool_present_routes_to_executor():
    state = {"error": None, "selected_tool": {"name": "x", "sql_template": "SELECT 1"}}
    assert _route_after_planner(state) == "sql_executor"


@pytest.mark.unit
def test_text_to_sql_success_routes_to_executor():
    assert _route_after_text_to_sql({"selected_tool": {"sql_template": "SELECT 1"}}) == "sql_executor"


@pytest.mark.unit
def test_text_to_sql_failure_routes_to_error():
    assert _route_after_text_to_sql({"error": "bad", "selected_tool": None}) == "error_handler"
    assert _route_after_text_to_sql({"selected_tool": None}) == "error_handler"


# ── SQL cleaning ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_clean_sql_strips_markdown_fence():
    raw = "```sql\nSELECT TOP 5 CardName FROM OCRD;\n```"
    assert _clean_sql(raw) == "SELECT TOP 5 CardName FROM OCRD"


@pytest.mark.unit
def test_clean_sql_strips_leading_prose():
    raw = "Here is the query:\nSELECT DocNum FROM OINV"
    assert _clean_sql(raw) == "SELECT DocNum FROM OINV"


@pytest.mark.unit
def test_clean_sql_keeps_cte():
    raw = "WITH t AS (SELECT 1 AS x) SELECT x FROM t;"
    assert _clean_sql(raw).startswith("WITH t AS")


@pytest.mark.unit
def test_clean_sql_handles_none_sentinel():
    assert _clean_sql("NONE") == "NONE"


# ── Reasoning trace ───────────────────────────────────────────────────────────

@pytest.mark.unit
def test_reasoning_includes_tool_and_intent():
    steps = _build_reasoning(
        intent="Aggregation", domain="sales", intent_reasoning="Asks for a sum.",
        is_text_to_sql=False, tool_name="sales_by_city", tables_used=["OINV", "INV1"],
        row_count=12, execution_ms=42,
    )
    blob = " ".join(steps)
    assert "Aggregation" in blob
    assert "sales" in blob
    assert "Asks for a sum." in blob
    assert "sales_by_city" in blob
    assert "OINV" in blob
    assert "12 row(s)" in blob and "42 ms" in blob


@pytest.mark.unit
def test_reasoning_marks_text_to_sql_fallback():
    steps = _build_reasoning(
        intent="Lookup", domain=None, intent_reasoning=None,
        is_text_to_sql=True, tool_name="ad_hoc_text_to_sql", tables_used=None,
        row_count=3, execution_ms=None,
    )
    blob = " ".join(steps)
    assert "generated a SQL query directly" in blob
    assert "3 row(s)" in blob
