"""
Unit tests — SAP B1 Tool Pack.

Spec: TG-003, TG-004
Tests:
  - Minimum 50 tools in the pack
  - All required fields present on every tool
  - Valid categories and domains
  - All SQL templates contain SELECT (no DDL/DML)
  - All SQL templates use :param_name syntax for parameters
  - Key tools are present (ar_invoice_total, dso_metric, customer_360, etc.)
  - input_schema parameters match SQL :param_name references
  - get_tool() lookup works case-insensitively
  - get_tools_by_domain() returns correct subset
  - get_tools_by_category() returns correct subset
"""

from __future__ import annotations

import re

import pytest

from app.services.tools.sap_b1_tools import (
    SAP_B1_TOOLS,
    get_tool,
    get_tools_by_category,
    get_tools_by_domain,
)

VALID_CATEGORIES = {"aggregate", "entity_summary", "filter", "trend", "kpi", "join"}
VALID_DOMAINS = {"finance", "sales", "purchasing", "inventory", "operations"}
REQUIRED_FIELDS = {"name", "description", "category", "domain",
                   "sql_template", "input_schema", "output_schema"}

KEY_TOOLS = [
    "ar_invoice_total",
    "ar_aging_summary",
    "dso_metric",
    "dpo_metric",
    "cash_conversion_cycle",
    "gross_profit_margin",
    "working_capital",
    "inventory_turnover",
    "on_time_delivery_rate",
    "customer_360",
    "sales_revenue_by_month",
    "top_customers_by_revenue",
    "top_vendors_by_spend",
    "inventory_stock_levels",
    "low_stock_items",
    "production_efficiency",
]


class TestPackCoverage:
    def test_minimum_50_tools(self):
        assert len(SAP_B1_TOOLS) >= 50, (
            f"Expected ≥50 tools, got {len(SAP_B1_TOOLS)}"
        )

    def test_no_duplicate_names(self):
        names = [t["name"] for t in SAP_B1_TOOLS]
        assert len(names) == len(set(names)), "Duplicate tool names found"

    @pytest.mark.parametrize("tool_name", KEY_TOOLS)
    def test_key_tools_present(self, tool_name):
        assert get_tool(tool_name) is not None, f"Missing key tool: {tool_name}"

    def test_get_tool_case_insensitive(self):
        assert get_tool("AR_INVOICE_TOTAL") is not None
        assert get_tool("Dso_Metric") is not None


class TestToolStructure:
    @pytest.mark.parametrize("tool", SAP_B1_TOOLS)
    def test_required_fields(self, tool):
        for field in REQUIRED_FIELDS:
            assert field in tool, f"Tool '{tool.get('name')}' missing field '{field}'"

    @pytest.mark.parametrize("tool", SAP_B1_TOOLS)
    def test_valid_category(self, tool):
        assert tool["category"] in VALID_CATEGORIES, (
            f"Tool '{tool['name']}' has invalid category '{tool['category']}'"
        )

    @pytest.mark.parametrize("tool", SAP_B1_TOOLS)
    def test_valid_domain(self, tool):
        assert tool["domain"] in VALID_DOMAINS, (
            f"Tool '{tool['name']}' has invalid domain '{tool['domain']}'"
        )

    @pytest.mark.parametrize("tool", SAP_B1_TOOLS)
    def test_sql_is_select_only(self, tool):
        sql_upper = tool["sql_template"].upper().strip()
        # Allow SQL comments at the top (KPI tools start with --)
        stripped = re.sub(r"--[^\n]*\n", "", sql_upper).strip()
        assert stripped.startswith("SELECT"), (
            f"Tool '{tool['name']}' SQL must start with SELECT"
        )

    @pytest.mark.parametrize("tool", SAP_B1_TOOLS)
    def test_no_dml_keywords(self, tool):
        sql_upper = tool["sql_template"].upper()
        forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER", "CREATE"]
        for kw in forbidden:
            # Word-boundary match so column names like CREATEDATE don't false-positive
            assert not re.search(rf"\b{kw}\b", sql_upper), (
                f"Tool '{tool['name']}' SQL contains forbidden keyword '{kw}'"
            )

    @pytest.mark.parametrize("tool", SAP_B1_TOOLS)
    def test_input_schema_is_list(self, tool):
        assert isinstance(tool["input_schema"], list), (
            f"Tool '{tool['name']}' input_schema must be a list"
        )

    @pytest.mark.parametrize("tool", SAP_B1_TOOLS)
    def test_input_schema_params_have_required_fields(self, tool):
        for param in tool["input_schema"]:
            assert "name" in param, f"Tool '{tool['name']}' param missing 'name'"
            assert "type" in param, f"Tool '{tool['name']}' param '{param.get('name')}' missing 'type'"
            assert "required" in param, f"Tool '{tool['name']}' param '{param.get('name')}' missing 'required'"

    @pytest.mark.parametrize("tool", SAP_B1_TOOLS)
    def test_sql_params_match_input_schema(self, tool):
        """Every :param_name in the SQL must be declared in input_schema."""
        sql_params = set(re.findall(r":([a-zA-Z_][a-zA-Z0-9_]*)", tool["sql_template"]))
        schema_names = {p["name"] for p in tool["input_schema"]}
        undeclared = sql_params - schema_names
        assert not undeclared, (
            f"Tool '{tool['name']}' SQL uses undeclared params: {undeclared}"
        )

    @pytest.mark.parametrize("tool", SAP_B1_TOOLS)
    def test_output_schema_has_columns_key(self, tool):
        assert "columns" in tool["output_schema"], (
            f"Tool '{tool['name']}' output_schema missing 'columns' key"
        )


class TestLookupFunctions:
    def test_get_tool_returns_none_for_unknown(self):
        assert get_tool("nonexistent_tool_xyz") is None

    def test_get_tools_by_domain_finance(self):
        tools = get_tools_by_domain("finance")
        assert len(tools) >= 8
        assert all(t["domain"] == "finance" for t in tools)

    def test_get_tools_by_domain_sales(self):
        tools = get_tools_by_domain("sales")
        assert len(tools) >= 6
        assert all(t["domain"] == "sales" for t in tools)

    def test_get_tools_by_domain_inventory(self):
        tools = get_tools_by_domain("inventory")
        assert len(tools) >= 5

    def test_get_tools_by_category_kpi(self):
        tools = get_tools_by_category("kpi")
        assert len(tools) >= 6
        assert all(t["category"] == "kpi" for t in tools)

    def test_get_tools_by_category_aggregate(self):
        tools = get_tools_by_category("aggregate")
        assert len(tools) >= 8

    def test_all_domains_represented(self):
        covered = {t["domain"] for t in SAP_B1_TOOLS}
        assert VALID_DOMAINS.issubset(covered), (
            f"Missing domains: {VALID_DOMAINS - covered}"
        )


class TestKeyToolSQLSignatures:
    """Spot-check that key tools contain expected SAP B1 table names."""

    def test_dso_uses_oinv(self):
        tool = get_tool("dso_metric")
        assert "OINV" in tool["sql_template"]

    def test_dpo_uses_opch(self):
        tool = get_tool("dpo_metric")
        assert "OPCH" in tool["sql_template"]

    def test_ar_aging_uses_oinv(self):
        tool = get_tool("ar_aging_summary")
        assert "OINV" in tool["sql_template"]
        assert "DATEDIFF" in tool["sql_template"].upper()

    def test_customer_360_uses_ocrd(self):
        tool = get_tool("customer_360")
        assert "OCRD" in tool["sql_template"]
        assert "OINV" in tool["sql_template"]
        assert "ORDR" in tool["sql_template"]

    def test_cash_conversion_cycle_has_all_components(self):
        tool = get_tool("cash_conversion_cycle")
        sql = tool["sql_template"]
        assert "OINV" in sql  # DSO
        assert "OPCH" in sql  # DPO
        assert "OITM" in sql  # DIO

    def test_inventory_stock_levels_uses_oitm_oitw(self):
        tool = get_tool("inventory_stock_levels")
        sql = tool["sql_template"]
        assert "OITM" in sql
        assert "OITW" in sql

    def test_on_time_delivery_uses_odln(self):
        tool = get_tool("on_time_delivery_rate")
        assert "ODLN" in tool["sql_template"]
