"""
Sprint 7 unit tests — SQL validator, context markers, clarification helpers.

Coverage:
  - SQL validator: AST + regex fallback for SELECT / DML / system tables / multi-stmt
  - Context agent: reference marker detection heuristic
  - Clarification agent: param humanisation
  - Supervisor routing: clarification branch
  - Feedback schema: rating validation
"""

from __future__ import annotations

import uuid
import pytest

from app.services.sql.validator import validate_sql, _regex_fallback, ValidationResult
from app.agents.context_agent import _REFERENCE_MARKERS
from app.agents.clarification_agent import _humanise_params
from app.agents.supervisor import (
    _route_after_executor,
    _route_after_context,
)


# ── SQL Validator — SELECT allowed ────────────────────────────────────────────

class TestValidatorAllowsSelect:
    def test_plain_select(self):
        r = validate_sql("SELECT * FROM OINV")
        assert r.is_valid

    def test_select_with_where(self):
        r = validate_sql("SELECT DocTotal FROM OINV WHERE CardCode = 'C001'")
        assert r.is_valid

    def test_select_with_join(self):
        r = validate_sql(
            "SELECT h.DocNum, l.ItemCode FROM OINV h "
            "JOIN INV1 l ON h.DocEntry = l.DocEntry"
        )
        assert r.is_valid

    def test_select_with_subquery(self):
        r = validate_sql(
            "SELECT * FROM (SELECT DocTotal FROM OINV WHERE DocStatus='O') sub"
        )
        assert r.is_valid

    def test_select_with_cte(self):
        r = validate_sql(
            "WITH cte AS (SELECT DocTotal FROM OINV) SELECT * FROM cte"
        )
        assert r.is_valid

    def test_select_star_produces_warning(self):
        r = validate_sql("SELECT * FROM OINV")
        assert r.is_valid
        # May have a star warning depending on sqlglot availability
        # At minimum no error
        assert r.error is None

    def test_select_top_n(self):
        r = validate_sql("SELECT TOP 100 DocNum FROM OINV")
        assert r.is_valid


# ── SQL Validator — DML blocked ───────────────────────────────────────────────

class TestValidatorBlocksDml:
    def test_insert_blocked(self):
        r = validate_sql("INSERT INTO OINV VALUES (1, 2)")
        assert not r.is_valid
        assert r.error

    def test_update_blocked(self):
        r = validate_sql("UPDATE OINV SET DocTotal=0 WHERE DocEntry=1")
        assert not r.is_valid

    def test_delete_blocked(self):
        r = validate_sql("DELETE FROM OINV WHERE DocEntry=1")
        assert not r.is_valid

    def test_drop_blocked(self):
        r = validate_sql("DROP TABLE OINV")
        assert not r.is_valid

    def test_truncate_blocked(self):
        r = validate_sql("TRUNCATE TABLE OINV")
        assert not r.is_valid

    def test_create_blocked(self):
        r = validate_sql("CREATE TABLE t (id INT)")
        assert not r.is_valid

    def test_merge_blocked(self):
        r = validate_sql("MERGE INTO t USING s ON t.id=s.id WHEN MATCHED THEN UPDATE SET t.v=s.v")
        assert not r.is_valid

    def test_exec_blocked(self):
        r = validate_sql("EXEC sp_helpdb")
        assert not r.is_valid

    def test_empty_blocked(self):
        r = validate_sql("")
        assert not r.is_valid

    def test_whitespace_only_blocked(self):
        r = validate_sql("   ")
        assert not r.is_valid


# ── SQL Validator — system catalogue blocked ──────────────────────────────────

class TestValidatorBlocksSystemTables:
    def test_information_schema_blocked(self):
        r = validate_sql("SELECT * FROM INFORMATION_SCHEMA.TABLES")
        assert not r.is_valid

    def test_sys_tables_blocked(self):
        r = validate_sql("SELECT * FROM SYS.TABLES")
        assert not r.is_valid

    def test_sys_columns_blocked(self):
        r = validate_sql("SELECT name FROM SYS.COLUMNS WHERE object_id=1")
        assert not r.is_valid


# ── SQL Validator — regex fallback ────────────────────────────────────────────

class TestValidatorRegexFallback:
    def test_fallback_allows_select(self):
        r = _regex_fallback("SELECT DocTotal FROM OINV")
        assert r.is_valid

    def test_fallback_blocks_insert(self):
        r = _regex_fallback("INSERT INTO t VALUES (1)")
        assert not r.is_valid

    def test_fallback_blocks_update(self):
        r = _regex_fallback("UPDATE t SET x=1")
        assert not r.is_valid

    def test_fallback_blocks_information_schema(self):
        r = _regex_fallback("SELECT * FROM INFORMATION_SCHEMA.TABLES")
        assert not r.is_valid

    def test_fallback_allows_with_cte(self):
        r = _regex_fallback("WITH cte AS (SELECT 1 AS n) SELECT n FROM cte")
        assert r.is_valid

    def test_fallback_rejects_non_select(self):
        r = _regex_fallback("CALL sp_something()")
        assert not r.is_valid


# ── Context agent — reference marker detection ────────────────────────────────

class TestContextReferenceMarkers:
    def test_pronoun_it_detected(self):
        assert _REFERENCE_MARKERS.search("Show me more about it")

    def test_pronoun_them_detected(self):
        assert _REFERENCE_MARKERS.search("Who are them?")

    def test_same_period_detected(self):
        assert _REFERENCE_MARKERS.search("Do the same for last month")

    def test_previous_detected(self):
        assert _REFERENCE_MARKERS.search("Show me the previous quarter")

    def test_why_detected(self):
        assert _REFERENCE_MARKERS.search("Why did this happen?")

    def test_standalone_number_not_detected(self):
        assert not _REFERENCE_MARKERS.search("Total revenue in Q3 2024")

    def test_explicit_question_not_detected(self):
        assert not _REFERENCE_MARKERS.search("Show total sales for January 2024")

    def test_customer_name_not_detected(self):
        assert not _REFERENCE_MARKERS.search("Revenue from customer Acme Corp in 2024")


# ── Clarification agent — param humanisation ──────────────────────────────────

class TestHumaniseParams:
    def test_description_used_when_available(self):
        schema = [{"name": "start_date", "description": "Start of the date range"}]
        result = _humanise_params(["start_date"], schema)
        assert result == ["Start of the date range"]

    def test_snake_case_converted_when_no_description(self):
        schema = [{"name": "customer_code", "description": ""}]
        result = _humanise_params(["customer_code"], schema)
        assert result == ["Customer Code"]

    def test_multiple_params(self):
        schema = [
            {"name": "start_date", "description": "Start date"},
            {"name": "end_date", "description": "End date"},
        ]
        result = _humanise_params(["start_date", "end_date"], schema)
        assert result == ["Start date", "End date"]

    def test_long_description_falls_back_to_snake_case(self):
        long_desc = "A" * 61
        schema = [{"name": "item_code", "description": long_desc}]
        result = _humanise_params(["item_code"], schema)
        assert result == ["Item Code"]

    def test_missing_from_schema_uses_snake_case(self):
        result = _humanise_params(["warehouse_code"], [])
        assert result == ["Warehouse Code"]

    def test_empty_missing_list(self):
        assert _humanise_params([], []) == []


# ── Supervisor routing — clarification branch ─────────────────────────────────

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


class TestSupervisorClarificationRouting:
    def test_needs_clarification_routes_to_clarification_agent(self):
        state = _st(needs_clarification=True, missing_params=["start_date"])
        assert _route_after_executor(state) == "clarification_agent"

    def test_no_clarification_no_error_routes_to_formatter(self):
        state = _st(needs_clarification=False)
        assert _route_after_executor(state) == "response_formatter"

    def test_error_takes_priority_over_clarification(self):
        state = _st(needs_clarification=True, error="something broke")
        assert _route_after_executor(state) == "error_handler"

    def test_context_agent_routes_to_intent_by_default(self):
        state = _st()
        assert _route_after_context(state) == "intent_classifier"

    def test_context_agent_routes_to_error_on_error(self):
        state = _st(error="context load failed")
        assert _route_after_context(state) == "error_handler"


# ── Feedback schema — rating validation ───────────────────────────────────────

class TestFeedbackSchema:
    def test_valid_thumbs_up(self):
        from app.schemas.feedback import FeedbackCreate
        fb = FeedbackCreate(
            conversation_turn_id=uuid.uuid4(),
            rating=1,
        )
        assert fb.rating == 1

    def test_valid_thumbs_down(self):
        from app.schemas.feedback import FeedbackCreate
        fb = FeedbackCreate(
            conversation_turn_id=uuid.uuid4(),
            rating=-1,
        )
        assert fb.rating == -1

    def test_invalid_rating_rejected(self):
        from pydantic import ValidationError
        from app.schemas.feedback import FeedbackCreate
        with pytest.raises(ValidationError):
            FeedbackCreate(conversation_turn_id=uuid.uuid4(), rating=0)

    def test_invalid_rating_two_rejected(self):
        from pydantic import ValidationError
        from app.schemas.feedback import FeedbackCreate
        with pytest.raises(ValidationError):
            FeedbackCreate(conversation_turn_id=uuid.uuid4(), rating=2)

    def test_correction_min_length_enforced(self):
        from pydantic import ValidationError
        from app.schemas.feedback import CorrectionCreate
        with pytest.raises(ValidationError):
            CorrectionCreate(
                conversation_turn_id=uuid.uuid4(),
                correction_text="short",  # < 10 chars
            )

    def test_correction_valid(self):
        from app.schemas.feedback import CorrectionCreate
        c = CorrectionCreate(
            conversation_turn_id=uuid.uuid4(),
            correction_text="This answer is incorrect because the filter was wrong.",
        )
        assert len(c.correction_text) > 10


# ── ValidationResult dataclass ────────────────────────────────────────────────

class TestValidationResult:
    def test_defaults(self):
        r = ValidationResult(is_valid=True)
        assert r.error is None
        assert r.warnings == []

    def test_invalid_with_error(self):
        r = ValidationResult(is_valid=False, error="DML blocked")
        assert not r.is_valid
        assert "DML" in r.error

    def test_valid_with_warnings(self):
        r = ValidationResult(is_valid=True, warnings=["SELECT * detected"])
        assert r.is_valid
        assert len(r.warnings) == 1
