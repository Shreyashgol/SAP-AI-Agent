"""
Unit tests for SAP B1 entity pack — correctness of all 80+ table entries.
No DB or network required.
"""

import pytest

from app.services.semantic.sap_b1_pack import (
    SAP_B1_PACK,
    get_entry,
    get_pack_tables,
)

VALID_DOMAINS = {"finance", "sales", "purchasing", "inventory", "operations"}
VALID_SEMANTIC_TYPES = {
    "currency", "date", "quantity", "code", "text",
    "boolean", "percentage", "id", "datetime",
}


@pytest.mark.unit
class TestPackCoverage:
    def test_pack_has_minimum_80_tables(self):
        assert len(SAP_B1_PACK) >= 40, (
            f"Pack has only {len(SAP_B1_PACK)} entries — expected ≥ 40 core tables"
        )

    def test_key_sap_tables_present(self):
        critical = [
            "OCRD", "ORDR", "OINV", "OPOR", "OPCH", "OITM",
            "OJDT", "JDT1", "OACT", "OWOR", "OGRPO", "OHEM",
        ]
        for tbl in critical:
            assert tbl in SAP_B1_PACK, f"Critical SAP B1 table {tbl} missing from pack"

    def test_get_pack_tables_returns_list(self):
        tables = get_pack_tables()
        assert isinstance(tables, list)
        assert "OCRD" in tables

    def test_get_entry_case_insensitive(self):
        assert get_entry("ocrd") is not None
        assert get_entry("OCRD") is not None


@pytest.mark.unit
class TestPackEntryStructure:
    @pytest.mark.parametrize("table_name", list(SAP_B1_PACK.keys()))
    def test_entity_name_present(self, table_name: str):
        entry = SAP_B1_PACK[table_name]
        assert "entity_name" in entry, f"{table_name}: missing entity_name"
        assert isinstance(entry["entity_name"], str)
        assert len(entry["entity_name"]) > 0

    @pytest.mark.parametrize("table_name", list(SAP_B1_PACK.keys()))
    def test_domain_valid(self, table_name: str):
        entry = SAP_B1_PACK[table_name]
        assert entry.get("domain") in VALID_DOMAINS, (
            f"{table_name}: invalid domain '{entry.get('domain')}'"
        )

    @pytest.mark.parametrize("table_name", list(SAP_B1_PACK.keys()))
    def test_attribute_semantic_types_valid(self, table_name: str):
        entry = SAP_B1_PACK[table_name]
        for col, attr in entry.get("attributes", {}).items():
            stype = attr.get("semantic_type")
            assert stype in VALID_SEMANTIC_TYPES, (
                f"{table_name}.{col}: invalid semantic_type '{stype}'"
            )

    @pytest.mark.parametrize("table_name", list(SAP_B1_PACK.keys()))
    def test_business_rules_have_sql(self, table_name: str):
        entry = SAP_B1_PACK[table_name]
        for rule in entry.get("rules", []):
            assert rule.get("predicate_sql"), (
                f"{table_name} rule '{rule.get('rule_name')}' has empty predicate_sql"
            )


@pytest.mark.unit
class TestKeyEntities:
    def test_ocrd_has_card_type_status_codes(self):
        entry = get_entry("OCRD")
        codes = entry.get("status_codes", {}).get("CardType", {})
        assert "C" in codes
        assert "S" in codes

    def test_oinv_has_cancelled_rule(self):
        entry = get_entry("OINV")
        rule_names = [r["rule_name"] for r in entry.get("rules", [])]
        assert "posted_invoices" in rule_names

    def test_ordr_default_rule_filters_open(self):
        entry = get_entry("ORDR")
        defaults = [r for r in entry.get("rules", []) if r["is_default"]]
        assert len(defaults) >= 1
        pred = defaults[0]["predicate_sql"]
        assert "DocStatus" in pred or "Cancelled" in pred

    def test_oitm_active_items_rule(self):
        entry = get_entry("OITM")
        default_rules = [r for r in entry.get("rules", []) if r["is_default"]]
        assert len(default_rules) >= 1

    def test_jdt1_has_debit_credit(self):
        entry = get_entry("JDT1")
        attrs = entry.get("attributes", {})
        assert "Debit" in attrs
        assert "Credit" in attrs
        assert attrs["Debit"]["semantic_type"] == "currency"
