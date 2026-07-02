"""
Tests for the ERPRef prior (SAP B1 onboarding warm-start).

These cover the pure extraction/intersection logic against the real reference
files in data/erpref_enriched_part*.json — no DB needed. The DB-bound apply()
is a thin wrapper around these helpers (fill-not-clobber writes + deduped edge
inserts), gated on a SAP B1 fingerprint by the task layer.
"""

import pytest

from app.services.semantic.erpref_prior import (
    column_descriptions,
    join_edges,
    load_prior,
    table_description,
)


@pytest.fixture(scope="module")
def prior() -> dict:
    return load_prior()


@pytest.fixture(scope="module")
def oinv(prior: dict) -> dict:
    return prior["OINV"]


# ── Loading ───────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_load_prior_has_core_b1_tables(prior: dict):
    for name in ("OINV", "INV1", "OCRD", "OITM"):
        assert name in prior, f"{name} missing from prior"
    # keyed by upper-cased table name
    assert all(k == k.upper() for k in prior)


@pytest.mark.unit
def test_load_prior_is_cached(prior: dict):
    assert load_prior() is prior  # lru_cache returns the same object


# ── Description extraction ─────────────────────────────────────────────────────

@pytest.mark.unit
def test_table_description_combines_name_and_desc(oinv: dict):
    desc = table_description(oinv)
    assert desc and oinv["business_name"] in desc


@pytest.mark.unit
def test_table_description_handles_missing_fields():
    assert table_description({"business_name": "Just A Name"}) == "Just A Name"
    assert table_description({"description": "Just a desc"}) == "Just a desc"
    assert table_description({}) is None


@pytest.mark.unit
def test_column_descriptions_keyed_upper(oinv: dict):
    cols = column_descriptions(oinv)
    assert "DOCENTRY" in cols  # OINV documents its primary key
    assert all(k == k.upper() for k in cols)


# ── Join-edge intersection (the safety-critical bit) ───────────────────────────

def _columns_from_joins(t: dict) -> dict[str, set[str]]:
    """Build a crawl-shaped column index that contains exactly the columns the
    prior's joins reference — i.e. a 'perfect crawl' where every edge is valid."""
    cols: dict[str, set[str]] = {}
    name = t["table_name"].upper()
    for j in t.get("joins", []):
        cols.setdefault(name, set()).add(j["from_column"].upper())
        cols.setdefault(j["to_table"].upper(), set()).add(j["to_column"].upper())
    return cols


@pytest.mark.unit
def test_join_edges_returned_when_all_legs_present(oinv: dict):
    cols = _columns_from_joins(oinv)
    edges = join_edges(oinv, cols)
    assert edges, "expected join edges for OINV"
    # OINV→OCRD on CardCode is a defining B1 relationship; it must survive.
    assert any(
        e["to_table"] == "OCRD" and e["from_column"] == "CARDCODE" for e in edges
    )
    for e in edges:
        assert e["from_table"] == "OINV"
        assert 0.0 <= e["confidence"] <= 1.0
        assert "purpose" in e  # plain-English hint surfaced to runtime


@pytest.mark.unit
def test_join_edges_carry_purpose(oinv: dict):
    cols = _columns_from_joins(oinv)
    edges = join_edges(oinv, cols)
    # At least one B1 join documents its purpose; it must be carried through.
    assert any(e["purpose"] for e in edges)


@pytest.mark.unit
def test_join_edges_drops_missing_target_table(oinv: dict):
    cols = _columns_from_joins(oinv)
    full = len(join_edges(oinv, cols))
    cols.pop("OCRD", None)  # pretend the crawl never found OCRD
    pruned = join_edges(oinv, cols)
    assert len(pruned) < full
    assert all(e["to_table"] != "OCRD" for e in pruned)


@pytest.mark.unit
def test_join_edges_drops_phantom_from_column(oinv: dict):
    cols = _columns_from_joins(oinv)
    cols["OINV"].discard("CARDCODE")  # column absent from this customer's crawl
    edges = join_edges(oinv, cols)
    assert all(e["from_column"] != "CARDCODE" for e in edges)


@pytest.mark.unit
def test_join_edges_empty_when_from_table_not_crawled(oinv: dict):
    assert join_edges(oinv, {"OCRD": {"CARDCODE"}}) == []
