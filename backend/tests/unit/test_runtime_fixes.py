"""
Regression tests for runtime bug fixes (complex-query stress testing).

Covers the pure-function fixes that unblock analytical queries:
  - query_planner._apply_date_defaults: undated date-range params default to an
    all-time window instead of forcing clarification; non-date params untouched.
  - trend_agent column detection: CamelCase SAP columns are normalised so the
    metric (TotalSales) is never confused with a period column (SalesYear), and
    year+month columns form a composite 'YYYY-MM' period label.
"""

import pytest

from app.agents.query_planner import _apply_date_defaults
from app.agents.trend_agent import _normalize, _extract_series, _pick_column, _find
from app.agents.trend_agent import _DATE_PATTERNS, _METRIC_PATTERNS


# ── query_planner._apply_date_defaults ────────────────────────────────────────

@pytest.mark.unit
def test_date_range_params_default_to_all_time():
    schema = [
        {"name": "date_from", "type": "date", "required": True},
        {"name": "date_to", "type": "date", "required": True},
    ]
    params = {"date_from": None, "date_to": None}
    _apply_date_defaults(schema, params, today="2026-06-17")
    assert params["date_from"] == "1900-01-01"
    assert params["date_to"] == "2026-06-17"


@pytest.mark.unit
def test_resolved_dates_are_not_overwritten():
    schema = [{"name": "date_from", "type": "date", "required": True}]
    params = {"date_from": "2025-01-01"}
    _apply_date_defaults(schema, params, today="2026-06-17")
    assert params["date_from"] == "2025-01-01"


@pytest.mark.unit
def test_non_date_param_left_for_clarification():
    schema = [{"name": "threshold", "type": "integer", "required": True}]
    params = {"threshold": None}
    _apply_date_defaults(schema, params, today="2026-06-17")
    assert params["threshold"] is None  # still missing → clarification


# ── trend_agent column detection ──────────────────────────────────────────────

@pytest.mark.unit
def test_normalize_splits_camelcase_and_snake():
    assert _normalize("SalesYear") == "sales year"
    assert _normalize("TotalSales") == "total sales"
    assert _normalize("doc_date") == "doc date"


@pytest.mark.unit
def test_camelcase_metric_not_mistaken_for_period():
    columns = ["SalesYear", "SalesMonth", "TotalSales", "InvoiceCount"]
    date_cols = [c for c in columns if _DATE_PATTERNS.search(_normalize(c))]
    assert date_cols == ["SalesYear", "SalesMonth"]
    metric_candidates = [c for c in columns if c not in date_cols]
    # TotalSales must win over the date columns — the old bug picked SalesMonth.
    assert _pick_column(metric_candidates, _METRIC_PATTERNS) == "TotalSales"


@pytest.mark.unit
def test_year_month_compose_into_period_label():
    rows = [
        {"SalesYear": 2025, "SalesMonth": 1, "TotalSales": 870000, "InvoiceCount": 5},
        {"SalesYear": 2025, "SalesMonth": 2, "TotalSales": 920000, "InvoiceCount": 6},
    ]
    series = _extract_series(
        rows, period_col="SalesYear", metric_col="TotalSales",
        year_col=_find(["SalesYear", "SalesMonth"], r"year"),
        month_col=_find(["SalesYear", "SalesMonth"], r"month"),
    )
    assert series == [
        {"label": "2025-01", "value": 870000.0},
        {"label": "2025-02", "value": 920000.0},
    ]
