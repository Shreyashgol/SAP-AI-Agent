"""
Unit tests for synonym engine, rules engine, and KPI library.
Uses fakeredis/in-memory patterns — no live DB.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.semantic.kpi_library import SYSTEM_KPIS
from app.services.semantic.synonym_engine import _DEFAULT_SYNONYMS


@pytest.mark.unit
class TestKPILibrary:
    def test_minimum_50_kpis_defined(self):
        assert len(SYSTEM_KPIS) >= 50, f"Only {len(SYSTEM_KPIS)} KPIs defined — need ≥ 50"

    def test_all_kpis_have_required_fields(self):
        required = {"name", "display_name", "domain", "aggregation_method"}
        for kpi in SYSTEM_KPIS:
            missing = required - set(kpi.keys())
            assert not missing, f"KPI '{kpi.get('name')}' missing fields: {missing}"

    def test_kpi_domains_valid(self):
        valid = {"finance", "sales", "purchasing", "inventory", "operations"}
        for kpi in SYSTEM_KPIS:
            assert kpi["domain"] in valid, (
                f"KPI '{kpi['name']}' has invalid domain '{kpi['domain']}'"
            )

    def test_kpi_aggregation_methods_valid(self):
        valid = {"sum", "avg", "count", "min", "max", "ratio"}
        for kpi in SYSTEM_KPIS:
            assert kpi["aggregation_method"] in valid, (
                f"KPI '{kpi['name']}' has invalid aggregation_method '{kpi['aggregation_method']}'"
            )

    def test_no_duplicate_kpi_names(self):
        names = [kpi["name"] for kpi in SYSTEM_KPIS]
        assert len(names) == len(set(names)), "Duplicate KPI names found"

    def test_finance_domain_has_key_kpis(self):
        names = {k["name"] for k in SYSTEM_KPIS}
        assert "total_revenue" in names
        assert "gross_profit" in names
        assert "accounts_receivable_balance" in names


@pytest.mark.unit
class TestSynonymEngine:
    def test_minimum_synonyms_defined(self):
        assert len(_DEFAULT_SYNONYMS) >= 40

    def test_synonym_tuples_valid_structure(self):
        valid_types = {"metric", "entity", "attribute"}
        for syn, canonical, etype in _DEFAULT_SYNONYMS:
            assert etype in valid_types, f"Invalid entity_type '{etype}' for synonym '{syn}'"
            assert len(syn) > 0
            assert len(canonical) > 0

    def test_key_synonyms_present(self):
        synonyms = {s[0].lower() for s in _DEFAULT_SYNONYMS}
        assert "revenue" in synonyms
        assert "customer" in synonyms
        assert "inventory" in synonyms
        assert "po" in synonyms
        assert "dso" in synonyms

    @pytest.mark.asyncio
    async def test_resolve_finds_synonym(self):
        from app.services.semantic.synonym_engine import SynonymEngine

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            MagicMock(synonym="revenue", entity_type="metric",
                      canonical_term="Total Revenue"),
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        engine = SynonymEngine(mock_db, uuid.uuid4())
        result = await engine.resolve("Revenue")
        assert result == "Total Revenue"

    @pytest.mark.asyncio
    async def test_resolve_returns_none_for_unknown(self):
        from app.services.semantic.synonym_engine import SynonymEngine

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        engine = SynonymEngine(mock_db, uuid.uuid4())
        result = await engine.resolve("xyzzy_nonexistent")
        assert result is None


@pytest.mark.unit
class TestRulesEngine:
    @pytest.mark.asyncio
    async def test_returns_empty_for_unknown_entity(self):
        from app.services.semantic.rules_engine import BusinessRulesEngine

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        engine = BusinessRulesEngine(mock_db, uuid.uuid4())
        preds = await engine.get_predicates_for_entity(uuid.uuid4())
        assert preds == []

    @pytest.mark.asyncio
    async def test_build_where_clause_with_no_rules(self):
        from app.services.semantic.rules_engine import BusinessRulesEngine

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        engine = BusinessRulesEngine(mock_db, uuid.uuid4())
        clause = await engine.build_where_clause(uuid.uuid4())
        assert clause == ""

    @pytest.mark.asyncio
    async def test_build_where_clause_combines_predicates(self):
        from app.services.semantic.rules_engine import BusinessRulesEngine
        from app.models.semantic import BusinessRule

        entity_id = uuid.uuid4()
        mock_rule = MagicMock(spec=BusinessRule)
        mock_rule.entity_id = entity_id
        mock_rule.predicate_sql = "\"Cancelled\" = 'N'"
        mock_rule.is_default = True

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_rule]
        mock_db.execute = AsyncMock(return_value=mock_result)

        engine = BusinessRulesEngine(mock_db, uuid.uuid4())
        clause = await engine.build_where_clause(entity_id)
        assert clause.startswith("WHERE")
        assert "Cancelled" in clause
