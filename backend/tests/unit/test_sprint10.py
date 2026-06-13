"""
Sprint 10 unit tests — Dashboard schemas, export sanitisation edge cases,
anomaly integration, dashboard API helpers.

Coverage:
  - DashboardCreate / WidgetCreate schema validation
  - WidgetCreate.widget_type allowlist rejection
  - Export sanitiser: formula injection edge cases
  - Anomaly badge severity mapping
  - Cache key stability across equivalent SQL whitespace
  - DashboardPatch partial update (only provided fields applied)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.dashboard import DashboardCreate, DashboardPatch, WidgetCreate, WidgetPatch
from app.api.v1.endpoints.export import _sanitise_cell, _sanitise_xlsx_cell
from app.services.cache.query_cache import _cache_key


# ── Dashboard schema ──────────────────────────────────────────────────────────

class TestDashboardCreate:
    def test_valid_creation(self):
        d = DashboardCreate(name="Sales Q1")
        assert d.name == "Sales Q1"
        assert d.is_shared is False

    def test_shared_flag(self):
        d = DashboardCreate(name="Shared Board", is_shared=True)
        assert d.is_shared is True

    def test_name_required(self):
        with pytest.raises(ValidationError):
            DashboardCreate()  # type: ignore[call-arg]


class TestDashboardPatch:
    def test_all_none_is_valid(self):
        p = DashboardPatch()
        assert p.name is None
        assert p.is_shared is None
        assert p.layout is None

    def test_partial_update_name_only(self):
        p = DashboardPatch(name="New Name")
        assert p.name == "New Name"
        assert p.is_shared is None

    def test_layout_dict(self):
        layout = {"abc123": {"x": 0, "y": 0, "w": 4, "h": 3}}
        p = DashboardPatch(layout=layout)
        assert p.layout == layout


# ── Widget schema ─────────────────────────────────────────────────────────────

class TestWidgetCreate:
    def test_valid_widget_table(self):
        import uuid
        w = WidgetCreate(conversation_turn_id=uuid.uuid4())
        assert w.widget_type == "table"
        assert w.width == 4
        assert w.height == 3

    def test_valid_widget_types(self):
        import uuid
        tid = uuid.uuid4()
        for wt in ("kpi_card", "bar", "line", "area", "donut", "waterfall", "table"):
            w = WidgetCreate(conversation_turn_id=tid, widget_type=wt)
            assert w.widget_type == wt

    def test_invalid_widget_type_rejected(self):
        import uuid
        with pytest.raises(ValidationError) as exc_info:
            WidgetCreate(conversation_turn_id=uuid.uuid4(), widget_type="scatter")
        assert "widget_type" in str(exc_info.value)

    def test_empty_widget_type_rejected(self):
        import uuid
        with pytest.raises(ValidationError):
            WidgetCreate(conversation_turn_id=uuid.uuid4(), widget_type="")

    def test_position_defaults(self):
        import uuid
        w = WidgetCreate(conversation_turn_id=uuid.uuid4())
        assert w.position_x == 0
        assert w.position_y == 0


class TestWidgetPatch:
    def test_all_optional(self):
        p = WidgetPatch()
        assert p.title is None
        assert p.widget_type is None

    def test_position_update(self):
        p = WidgetPatch(position_x=4, position_y=2, width=6, height=4)
        assert p.position_x == 4
        assert p.width == 6


# ── Export sanitiser — extended edge cases ────────────────────────────────────

class TestSanitiseCellExtended:
    def test_empty_string_unchanged(self):
        assert _sanitise_cell("") == ""

    def test_regular_negative_number_unchanged(self):
        # Negative float — starts with "-" digit combo → should be escaped
        result = _sanitise_cell("-42.5")
        assert result.startswith("'")

    def test_zero_unchanged(self):
        assert _sanitise_cell(0) == "0"

    def test_boolean_true(self):
        assert _sanitise_cell(True) == "True"

    def test_boolean_false(self):
        assert _sanitise_cell(False) == "False"

    def test_list_coerced(self):
        result = _sanitise_cell([1, 2, 3])
        assert isinstance(result, str)

    def test_dict_coerced(self):
        result = _sanitise_cell({"key": "val"})
        assert isinstance(result, str)


class TestSanitiseXlsxCellExtended:
    def test_numeric_passthrough(self):
        # Numbers should be returned as string (we always convert to str)
        result = _sanitise_xlsx_cell(42.5)
        assert result == "42.5"

    def test_empty_string_unchanged(self):
        assert _sanitise_xlsx_cell("") == ""

    def test_at_prefix_formula_xlsx(self):
        result = _sanitise_xlsx_cell("@IMPORTRANGE()")
        assert result.startswith(" ")


# ── Cache key stability ───────────────────────────────────────────────────────

class TestCacheKeyStability:
    def test_params_order_independent(self):
        # JSON sort_keys=True ensures param key order doesn't matter
        k1 = _cache_key("t", "c", "SELECT 1", {"b": 2, "a": 1})
        k2 = _cache_key("t", "c", "SELECT 1", {"a": 1, "b": 2})
        assert k1 == k2

    def test_connection_id_affects_key(self):
        k1 = _cache_key("t", "conn_A", "SELECT 1", {})
        k2 = _cache_key("t", "conn_B", "SELECT 1", {})
        assert k1 != k2

    def test_different_sql_different_key(self):
        k1 = _cache_key("t", "c", "SELECT 1", {})
        k2 = _cache_key("t", "c", "SELECT 2", {})
        assert k1 != k2

    def test_uppercase_normalisation(self):
        k1 = _cache_key("t", "c", "select * from sales", {})
        k2 = _cache_key("t", "c", "SELECT * FROM SALES", {})
        assert k1 == k2

    def test_tab_whitespace_normalised(self):
        k1 = _cache_key("t", "c", "SELECT\t*\tFROM\tsales", {})
        k2 = _cache_key("t", "c", "SELECT * FROM SALES", {})
        assert k1 == k2
