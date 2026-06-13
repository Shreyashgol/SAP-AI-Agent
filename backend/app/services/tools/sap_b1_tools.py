"""
SAP Business One Tool Pack — 50 parameterised SQL tool templates.

Spec: TG-003, TG-004
Coverage: Finance, Sales, Purchasing, Inventory, Operations, CRM

These are loaded by PackLoader.apply_tool_pack() and stored as Tool records
with pack_source="sap_b1" and is_system=True.

Each entry defines:
  name         — unique tool identifier (snake_case)
  description  — plain-English description for NLU tool selection
  category     — aggregate | entity_summary | filter | trend | kpi | join
  domain       — finance | sales | purchasing | inventory | operations
  sql_template — parameterised SQL; use :param_name for user inputs
  input_schema — list of {name, type, required, default?, description}
  output_schema— {columns: [{name, type}]}
"""

from __future__ import annotations

from typing import Any

SAP_B1_TOOLS: list[dict[str, Any]] = [

    # ────────────────────────────────────────────────────────
    # FINANCE
    # ────────────────────────────────────────────────────────
    {
        "name": "ar_invoice_total",
        "description": "Total AR invoice amount for a date range.",
        "category": "aggregate",
        "domain": "finance",
        "sql_template": (
            "SELECT SUM(DocTotal) AS total_amount, COUNT(*) AS invoice_count\n"
            "FROM OINV\n"
            "WHERE DocDate BETWEEN :date_from AND :date_to\n"
            "  AND CANCELLED = 'N'"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date", "required": True, "description": "Start date"},
            {"name": "date_to",   "type": "date", "required": True, "description": "End date"},
        ],
        "output_schema": {"columns": [
            {"name": "total_amount",   "type": "number"},
            {"name": "invoice_count",  "type": "integer"},
        ]},
    },
    {
        "name": "ar_invoice_by_customer",
        "description": "AR invoices for a specific business partner.",
        "category": "filter",
        "domain": "finance",
        "sql_template": (
            "SELECT T0.DocNum, T0.DocDate, T0.DocDueDate, T0.CardCode, T0.CardName,\n"
            "       T0.DocTotal, T0.PaidToDate, T0.DocTotal - T0.PaidToDate AS BalanceDue,\n"
            "       T0.DocCur, T0.DocStatus\n"
            "FROM OINV T0\n"
            "WHERE T0.CardCode = :card_code\n"
            "  AND T0.CANCELLED = 'N'\n"
            "ORDER BY T0.DocDate DESC"
        ),
        "input_schema": [
            {"name": "card_code", "type": "string", "required": True, "description": "Business partner code"},
        ],
        "output_schema": {"columns": [
            {"name": "DocNum",      "type": "string"},
            {"name": "DocDate",     "type": "date"},
            {"name": "CardName",    "type": "string"},
            {"name": "DocTotal",    "type": "number"},
            {"name": "BalanceDue",  "type": "number"},
            {"name": "DocStatus",   "type": "string"},
        ]},
    },
    {
        "name": "ar_aging_summary",
        "description": "AR aging buckets: current, 30, 60, 90+ days overdue.",
        "category": "kpi",
        "domain": "finance",
        "sql_template": (
            "SELECT\n"
            "  SUM(CASE WHEN DATEDIFF(day, DocDueDate, :as_of_date) <= 0    THEN DocTotal - PaidToDate ELSE 0 END) AS current_amount,\n"
            "  SUM(CASE WHEN DATEDIFF(day, DocDueDate, :as_of_date) BETWEEN 1  AND 30  THEN DocTotal - PaidToDate ELSE 0 END) AS days_1_30,\n"
            "  SUM(CASE WHEN DATEDIFF(day, DocDueDate, :as_of_date) BETWEEN 31 AND 60  THEN DocTotal - PaidToDate ELSE 0 END) AS days_31_60,\n"
            "  SUM(CASE WHEN DATEDIFF(day, DocDueDate, :as_of_date) BETWEEN 61 AND 90  THEN DocTotal - PaidToDate ELSE 0 END) AS days_61_90,\n"
            "  SUM(CASE WHEN DATEDIFF(day, DocDueDate, :as_of_date) > 90              THEN DocTotal - PaidToDate ELSE 0 END) AS over_90\n"
            "FROM OINV\n"
            "WHERE CANCELLED = 'N' AND DocTotal > PaidToDate"
        ),
        "input_schema": [
            {"name": "as_of_date", "type": "date", "required": True, "description": "Aging as-of date"},
        ],
        "output_schema": {"columns": [
            {"name": "current_amount", "type": "number"},
            {"name": "days_1_30",      "type": "number"},
            {"name": "days_31_60",     "type": "number"},
            {"name": "days_61_90",     "type": "number"},
            {"name": "over_90",        "type": "number"},
        ]},
    },
    {
        "name": "journal_entries_by_account",
        "description": "Journal entry lines posted to a specific GL account.",
        "category": "filter",
        "domain": "finance",
        "sql_template": (
            "SELECT T0.TransId, T0.RefDate, T1.Account, T1.Debit, T1.Credit,\n"
            "       T1.LineMemo, T0.Memo\n"
            "FROM OJDT T0\n"
            "JOIN JDT1 T1 ON T0.TransId = T1.TransId\n"
            "WHERE T1.Account = :account_code\n"
            "  AND T0.RefDate BETWEEN :date_from AND :date_to\n"
            "ORDER BY T0.RefDate DESC"
        ),
        "input_schema": [
            {"name": "account_code", "type": "string", "required": True, "description": "G/L account code"},
            {"name": "date_from",    "type": "date",   "required": True, "description": "Start date"},
            {"name": "date_to",      "type": "date",   "required": True, "description": "End date"},
        ],
        "output_schema": {"columns": [
            {"name": "TransId",  "type": "string"},
            {"name": "RefDate",  "type": "date"},
            {"name": "Account",  "type": "string"},
            {"name": "Debit",    "type": "number"},
            {"name": "Credit",   "type": "number"},
            {"name": "LineMemo", "type": "string"},
        ]},
    },
    {
        "name": "account_balance",
        "description": "Current balance of a G/L account.",
        "category": "aggregate",
        "domain": "finance",
        "sql_template": (
            "SELECT T0.AcctCode, T0.AcctName,\n"
            "       SUM(T1.Debit) - SUM(T1.Credit) AS balance\n"
            "FROM OACT T0\n"
            "JOIN JDT1 T1 ON T0.AcctCode = T1.Account\n"
            "WHERE T0.AcctCode = :account_code\n"
            "GROUP BY T0.AcctCode, T0.AcctName"
        ),
        "input_schema": [
            {"name": "account_code", "type": "string", "required": True, "description": "G/L account code"},
        ],
        "output_schema": {"columns": [
            {"name": "AcctCode", "type": "string"},
            {"name": "AcctName", "type": "string"},
            {"name": "balance",  "type": "number"},
        ]},
    },
    {
        "name": "ap_invoice_total",
        "description": "Total AP invoice amount for a date range.",
        "category": "aggregate",
        "domain": "finance",
        "sql_template": (
            "SELECT SUM(DocTotal) AS total_amount, COUNT(*) AS invoice_count\n"
            "FROM OPCH\n"
            "WHERE DocDate BETWEEN :date_from AND :date_to\n"
            "  AND CANCELLED = 'N'"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date", "required": True, "description": "Start date"},
            {"name": "date_to",   "type": "date", "required": True, "description": "End date"},
        ],
        "output_schema": {"columns": [
            {"name": "total_amount",  "type": "number"},
            {"name": "invoice_count", "type": "integer"},
        ]},
    },
    {
        "name": "ap_aging_summary",
        "description": "AP aging buckets: current, 30, 60, 90+ days overdue.",
        "category": "kpi",
        "domain": "finance",
        "sql_template": (
            "SELECT\n"
            "  SUM(CASE WHEN DATEDIFF(day, DocDueDate, :as_of_date) <= 0   THEN DocTotal - PaidToDate ELSE 0 END) AS current_amount,\n"
            "  SUM(CASE WHEN DATEDIFF(day, DocDueDate, :as_of_date) BETWEEN 1  AND 30 THEN DocTotal - PaidToDate ELSE 0 END) AS days_1_30,\n"
            "  SUM(CASE WHEN DATEDIFF(day, DocDueDate, :as_of_date) BETWEEN 31 AND 60 THEN DocTotal - PaidToDate ELSE 0 END) AS days_31_60,\n"
            "  SUM(CASE WHEN DATEDIFF(day, DocDueDate, :as_of_date) BETWEEN 61 AND 90 THEN DocTotal - PaidToDate ELSE 0 END) AS days_61_90,\n"
            "  SUM(CASE WHEN DATEDIFF(day, DocDueDate, :as_of_date) > 90             THEN DocTotal - PaidToDate ELSE 0 END) AS over_90\n"
            "FROM OPCH\n"
            "WHERE CANCELLED = 'N' AND DocTotal > PaidToDate"
        ),
        "input_schema": [
            {"name": "as_of_date", "type": "date", "required": True, "description": "Aging as-of date"},
        ],
        "output_schema": {"columns": [
            {"name": "current_amount", "type": "number"},
            {"name": "days_1_30",      "type": "number"},
            {"name": "days_31_60",     "type": "number"},
            {"name": "days_61_90",     "type": "number"},
            {"name": "over_90",        "type": "number"},
        ]},
    },
    {
        "name": "dso_metric",
        "description": "Days Sales Outstanding (DSO) for a period.",
        "category": "kpi",
        "domain": "finance",
        "sql_template": (
            "SELECT\n"
            "  SUM(T0.DocTotal - T0.PaidToDate) AS ar_balance,\n"
            "  SUM(T0.DocTotal) / NULLIF(DATEDIFF(day, :date_from, :date_to), 0) AS avg_daily_sales,\n"
            "  (SUM(T0.DocTotal - T0.PaidToDate))\n"
            "    / NULLIF(SUM(T0.DocTotal) / NULLIF(DATEDIFF(day, :date_from, :date_to), 0), 0) AS dso_days\n"
            "FROM OINV T0\n"
            "WHERE T0.DocDate BETWEEN :date_from AND :date_to\n"
            "  AND T0.CANCELLED = 'N'"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date", "required": True, "description": "Period start"},
            {"name": "date_to",   "type": "date", "required": True, "description": "Period end"},
        ],
        "output_schema": {"columns": [
            {"name": "ar_balance",       "type": "number"},
            {"name": "avg_daily_sales",  "type": "number"},
            {"name": "dso_days",         "type": "number"},
        ]},
    },

    # ────────────────────────────────────────────────────────
    # SALES
    # ────────────────────────────────────────────────────────
    {
        "name": "sales_order_summary",
        "description": "Sales orders for a date range with status breakdown.",
        "category": "aggregate",
        "domain": "sales",
        "sql_template": (
            "SELECT DocStatus,\n"
            "       COUNT(*) AS order_count,\n"
            "       SUM(DocTotal) AS total_value\n"
            "FROM ORDR\n"
            "WHERE DocDate BETWEEN :date_from AND :date_to\n"
            "  AND CANCELLED = 'N'\n"
            "GROUP BY DocStatus\n"
            "ORDER BY DocStatus"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date", "required": True, "description": "Start date"},
            {"name": "date_to",   "type": "date", "required": True, "description": "End date"},
        ],
        "output_schema": {"columns": [
            {"name": "DocStatus",   "type": "string"},
            {"name": "order_count", "type": "integer"},
            {"name": "total_value", "type": "number"},
        ]},
    },
    {
        "name": "sales_order_by_customer",
        "description": "Sales orders for a specific business partner.",
        "category": "filter",
        "domain": "sales",
        "sql_template": (
            "SELECT DocNum, DocDate, DocDueDate, CardCode, CardName,\n"
            "       DocTotal, DocCur, DocStatus, SlpCode\n"
            "FROM ORDR\n"
            "WHERE CardCode = :card_code\n"
            "  AND CANCELLED = 'N'\n"
            "ORDER BY DocDate DESC"
        ),
        "input_schema": [
            {"name": "card_code", "type": "string", "required": True, "description": "Customer code"},
        ],
        "output_schema": {"columns": [
            {"name": "DocNum",    "type": "string"},
            {"name": "DocDate",   "type": "date"},
            {"name": "CardName",  "type": "string"},
            {"name": "DocTotal",  "type": "number"},
            {"name": "DocStatus", "type": "string"},
        ]},
    },
    {
        "name": "sales_revenue_by_month",
        "description": "Monthly sales revenue trend (AR invoices).",
        "category": "trend",
        "domain": "sales",
        "sql_template": (
            "SELECT YEAR(DocDate) AS year, MONTH(DocDate) AS month,\n"
            "       SUM(DocTotal) AS revenue,\n"
            "       COUNT(*) AS invoice_count\n"
            "FROM OINV\n"
            "WHERE DocDate BETWEEN :date_from AND :date_to\n"
            "  AND CANCELLED = 'N'\n"
            "GROUP BY YEAR(DocDate), MONTH(DocDate)\n"
            "ORDER BY year, month"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date", "required": True, "description": "Start date"},
            {"name": "date_to",   "type": "date", "required": True, "description": "End date"},
        ],
        "output_schema": {"columns": [
            {"name": "year",          "type": "integer"},
            {"name": "month",         "type": "integer"},
            {"name": "revenue",       "type": "number"},
            {"name": "invoice_count", "type": "integer"},
        ]},
    },
    {
        "name": "top_customers_by_revenue",
        "description": "Top N customers by total invoice revenue.",
        "category": "aggregate",
        "domain": "sales",
        "sql_template": (
            "SELECT TOP :limit\n"
            "       T0.CardCode, T0.CardName,\n"
            "       SUM(T1.DocTotal) AS total_revenue,\n"
            "       COUNT(T1.DocNum) AS invoice_count\n"
            "FROM OCRD T0\n"
            "JOIN OINV T1 ON T0.CardCode = T1.CardCode\n"
            "WHERE T1.DocDate BETWEEN :date_from AND :date_to\n"
            "  AND T1.CANCELLED = 'N'\n"
            "GROUP BY T0.CardCode, T0.CardName\n"
            "ORDER BY total_revenue DESC"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date",    "required": True,  "description": "Start date"},
            {"name": "date_to",   "type": "date",    "required": True,  "description": "End date"},
            {"name": "limit",     "type": "integer", "required": False, "default": 10, "description": "Top N"},
        ],
        "output_schema": {"columns": [
            {"name": "CardCode",       "type": "string"},
            {"name": "CardName",       "type": "string"},
            {"name": "total_revenue",  "type": "number"},
            {"name": "invoice_count",  "type": "integer"},
        ]},
    },
    {
        "name": "sales_by_salesperson",
        "description": "Revenue breakdown by sales representative.",
        "category": "aggregate",
        "domain": "sales",
        "sql_template": (
            "SELECT T1.SlpCode, T1.SlpName,\n"
            "       SUM(T0.DocTotal) AS total_revenue,\n"
            "       COUNT(*) AS invoice_count\n"
            "FROM OINV T0\n"
            "JOIN OSLP T1 ON T0.SlpCode = T1.SlpCode\n"
            "WHERE T0.DocDate BETWEEN :date_from AND :date_to\n"
            "  AND T0.CANCELLED = 'N'\n"
            "GROUP BY T1.SlpCode, T1.SlpName\n"
            "ORDER BY total_revenue DESC"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date", "required": True, "description": "Start date"},
            {"name": "date_to",   "type": "date", "required": True, "description": "End date"},
        ],
        "output_schema": {"columns": [
            {"name": "SlpCode",       "type": "string"},
            {"name": "SlpName",       "type": "string"},
            {"name": "total_revenue", "type": "number"},
            {"name": "invoice_count", "type": "integer"},
        ]},
    },
    {
        "name": "quotation_conversion_rate",
        "description": "Sales quotation to order conversion rate.",
        "category": "kpi",
        "domain": "sales",
        "sql_template": (
            "SELECT\n"
            "  COUNT(DISTINCT T0.DocNum) AS quotation_count,\n"
            "  COUNT(DISTINCT T1.DocNum) AS order_count,\n"
            "  CAST(COUNT(DISTINCT T1.DocNum) AS FLOAT)\n"
            "    / NULLIF(COUNT(DISTINCT T0.DocNum), 0) * 100 AS conversion_pct\n"
            "FROM OQUT T0\n"
            "LEFT JOIN ORDR T1 ON T0.DocNum = T1.BsDocNum\n"
            "WHERE T0.DocDate BETWEEN :date_from AND :date_to\n"
            "  AND T0.CANCELLED = 'N'"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date", "required": True, "description": "Start date"},
            {"name": "date_to",   "type": "date", "required": True, "description": "End date"},
        ],
        "output_schema": {"columns": [
            {"name": "quotation_count",  "type": "integer"},
            {"name": "order_count",      "type": "integer"},
            {"name": "conversion_pct",   "type": "number"},
        ]},
    },
    {
        "name": "open_deliveries",
        "description": "Delivery orders not yet fully invoiced.",
        "category": "entity_summary",
        "domain": "sales",
        "sql_template": (
            "SELECT DocNum, DocDate, CardCode, CardName, DocTotal, DocStatus\n"
            "FROM ODLN\n"
            "WHERE DocStatus = 'O'\n"
            "  AND CANCELLED = 'N'\n"
            "  AND DocDate <= :as_of_date\n"
            "ORDER BY DocDate ASC"
        ),
        "input_schema": [
            {"name": "as_of_date", "type": "date", "required": True, "description": "As-of date"},
        ],
        "output_schema": {"columns": [
            {"name": "DocNum",    "type": "string"},
            {"name": "DocDate",   "type": "date"},
            {"name": "CardName",  "type": "string"},
            {"name": "DocTotal",  "type": "number"},
            {"name": "DocStatus", "type": "string"},
        ]},
    },

    # ────────────────────────────────────────────────────────
    # PURCHASING
    # ────────────────────────────────────────────────────────
    {
        "name": "purchase_order_summary",
        "description": "Purchase order totals by status for a date range.",
        "category": "aggregate",
        "domain": "purchasing",
        "sql_template": (
            "SELECT DocStatus,\n"
            "       COUNT(*) AS po_count,\n"
            "       SUM(DocTotal) AS total_value\n"
            "FROM OPOR\n"
            "WHERE DocDate BETWEEN :date_from AND :date_to\n"
            "  AND CANCELLED = 'N'\n"
            "GROUP BY DocStatus"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date", "required": True, "description": "Start date"},
            {"name": "date_to",   "type": "date", "required": True, "description": "End date"},
        ],
        "output_schema": {"columns": [
            {"name": "DocStatus",  "type": "string"},
            {"name": "po_count",   "type": "integer"},
            {"name": "total_value","type": "number"},
        ]},
    },
    {
        "name": "purchase_order_by_vendor",
        "description": "Purchase orders for a specific vendor.",
        "category": "filter",
        "domain": "purchasing",
        "sql_template": (
            "SELECT DocNum, DocDate, DocDueDate, CardCode, CardName,\n"
            "       DocTotal, DocCur, DocStatus\n"
            "FROM OPOR\n"
            "WHERE CardCode = :card_code\n"
            "  AND CANCELLED = 'N'\n"
            "ORDER BY DocDate DESC"
        ),
        "input_schema": [
            {"name": "card_code", "type": "string", "required": True, "description": "Vendor code"},
        ],
        "output_schema": {"columns": [
            {"name": "DocNum",    "type": "string"},
            {"name": "DocDate",   "type": "date"},
            {"name": "CardName",  "type": "string"},
            {"name": "DocTotal",  "type": "number"},
            {"name": "DocStatus", "type": "string"},
        ]},
    },
    {
        "name": "top_vendors_by_spend",
        "description": "Top N vendors by total AP invoice spend.",
        "category": "aggregate",
        "domain": "purchasing",
        "sql_template": (
            "SELECT TOP :limit\n"
            "       T0.CardCode, T0.CardName,\n"
            "       SUM(T1.DocTotal) AS total_spend,\n"
            "       COUNT(T1.DocNum) AS invoice_count\n"
            "FROM OCRD T0\n"
            "JOIN OPCH T1 ON T0.CardCode = T1.CardCode\n"
            "WHERE T1.DocDate BETWEEN :date_from AND :date_to\n"
            "  AND T1.CANCELLED = 'N'\n"
            "GROUP BY T0.CardCode, T0.CardName\n"
            "ORDER BY total_spend DESC"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date",    "required": True,  "description": "Start date"},
            {"name": "date_to",   "type": "date",    "required": True,  "description": "End date"},
            {"name": "limit",     "type": "integer", "required": False, "default": 10, "description": "Top N"},
        ],
        "output_schema": {"columns": [
            {"name": "CardCode",    "type": "string"},
            {"name": "CardName",    "type": "string"},
            {"name": "total_spend", "type": "number"},
        ]},
    },
    {
        "name": "dpo_metric",
        "description": "Days Payable Outstanding (DPO) for a period.",
        "category": "kpi",
        "domain": "purchasing",
        "sql_template": (
            "SELECT\n"
            "  SUM(T0.DocTotal - T0.PaidToDate) AS ap_balance,\n"
            "  SUM(T0.DocTotal) / NULLIF(DATEDIFF(day, :date_from, :date_to), 0) AS avg_daily_purchases,\n"
            "  (SUM(T0.DocTotal - T0.PaidToDate))\n"
            "    / NULLIF(SUM(T0.DocTotal) / NULLIF(DATEDIFF(day, :date_from, :date_to), 0), 0) AS dpo_days\n"
            "FROM OPCH T0\n"
            "WHERE T0.DocDate BETWEEN :date_from AND :date_to\n"
            "  AND T0.CANCELLED = 'N'"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date", "required": True, "description": "Period start"},
            {"name": "date_to",   "type": "date", "required": True, "description": "Period end"},
        ],
        "output_schema": {"columns": [
            {"name": "ap_balance",          "type": "number"},
            {"name": "avg_daily_purchases", "type": "number"},
            {"name": "dpo_days",            "type": "number"},
        ]},
    },
    {
        "name": "overdue_purchase_orders",
        "description": "Purchase orders past their due date and still open.",
        "category": "entity_summary",
        "domain": "purchasing",
        "sql_template": (
            "SELECT DocNum, DocDate, DocDueDate, CardCode, CardName, DocTotal\n"
            "FROM OPOR\n"
            "WHERE DocStatus = 'O'\n"
            "  AND DocDueDate < :as_of_date\n"
            "  AND CANCELLED = 'N'\n"
            "ORDER BY DocDueDate ASC"
        ),
        "input_schema": [
            {"name": "as_of_date", "type": "date", "required": True, "description": "As-of date"},
        ],
        "output_schema": {"columns": [
            {"name": "DocNum",      "type": "string"},
            {"name": "DocDueDate",  "type": "date"},
            {"name": "CardName",    "type": "string"},
            {"name": "DocTotal",    "type": "number"},
        ]},
    },
    {
        "name": "goods_receipt_summary",
        "description": "Goods receipts (OPDN) for a date range.",
        "category": "aggregate",
        "domain": "purchasing",
        "sql_template": (
            "SELECT COUNT(*) AS receipt_count, SUM(DocTotal) AS total_value\n"
            "FROM OPDN\n"
            "WHERE DocDate BETWEEN :date_from AND :date_to\n"
            "  AND CANCELLED = 'N'"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date", "required": True, "description": "Start date"},
            {"name": "date_to",   "type": "date", "required": True, "description": "End date"},
        ],
        "output_schema": {"columns": [
            {"name": "receipt_count", "type": "integer"},
            {"name": "total_value",   "type": "number"},
        ]},
    },

    # ────────────────────────────────────────────────────────
    # INVENTORY
    # ────────────────────────────────────────────────────────
    {
        "name": "inventory_stock_levels",
        "description": "Current on-hand stock levels by item and warehouse.",
        "category": "entity_summary",
        "domain": "inventory",
        "sql_template": (
            "SELECT T0.ItemCode, T0.ItemName, T1.WhsCode,\n"
            "       T1.OnHand, T1.IsCommited, T1.OnOrder,\n"
            "       T1.OnHand - T1.IsCommited + T1.OnOrder AS available_qty\n"
            "FROM OITM T0\n"
            "JOIN OITW T1 ON T0.ItemCode = T1.ItemCode\n"
            "WHERE T0.validFor = 'Y'\n"
            "  AND (:warehouse_code IS NULL OR T1.WhsCode = :warehouse_code)\n"
            "ORDER BY T0.ItemCode"
        ),
        "input_schema": [
            {"name": "warehouse_code", "type": "string", "required": False,
             "default": None, "description": "Filter by warehouse (optional)"},
        ],
        "output_schema": {"columns": [
            {"name": "ItemCode",      "type": "string"},
            {"name": "ItemName",      "type": "string"},
            {"name": "WhsCode",       "type": "string"},
            {"name": "OnHand",        "type": "number"},
            {"name": "IsCommited",    "type": "number"},
            {"name": "available_qty", "type": "number"},
        ]},
    },
    {
        "name": "low_stock_items",
        "description": "Items where on-hand quantity falls below minimum stock level.",
        "category": "entity_summary",
        "domain": "inventory",
        "sql_template": (
            "SELECT T0.ItemCode, T0.ItemName, T1.WhsCode,\n"
            "       T1.OnHand, T1.MinStock,\n"
            "       T1.MinStock - T1.OnHand AS shortage_qty\n"
            "FROM OITM T0\n"
            "JOIN OITW T1 ON T0.ItemCode = T1.ItemCode\n"
            "WHERE T0.validFor = 'Y'\n"
            "  AND T1.OnHand < T1.MinStock\n"
            "  AND T1.MinStock > 0\n"
            "ORDER BY shortage_qty DESC"
        ),
        "input_schema": [],
        "output_schema": {"columns": [
            {"name": "ItemCode",     "type": "string"},
            {"name": "ItemName",     "type": "string"},
            {"name": "WhsCode",      "type": "string"},
            {"name": "OnHand",       "type": "number"},
            {"name": "MinStock",     "type": "number"},
            {"name": "shortage_qty", "type": "number"},
        ]},
    },
    {
        "name": "inventory_valuation",
        "description": "Total inventory valuation by item group.",
        "category": "aggregate",
        "domain": "inventory",
        "sql_template": (
            "SELECT T1.ItmsGrpNam AS item_group,\n"
            "       SUM(T0.OnHand * T0.AvgPrice) AS total_value,\n"
            "       COUNT(DISTINCT T0.ItemCode) AS item_count\n"
            "FROM OITM T0\n"
            "JOIN OITB T1 ON T0.ItmsGrpCod = T1.ItmsGrpCod\n"
            "WHERE T0.validFor = 'Y'\n"
            "GROUP BY T1.ItmsGrpNam\n"
            "ORDER BY total_value DESC"
        ),
        "input_schema": [],
        "output_schema": {"columns": [
            {"name": "item_group",  "type": "string"},
            {"name": "total_value", "type": "number"},
            {"name": "item_count",  "type": "integer"},
        ]},
    },
    {
        "name": "inventory_turnover",
        "description": "Inventory turnover ratio (COGS / average inventory) for a period.",
        "category": "kpi",
        "domain": "inventory",
        "sql_template": (
            "SELECT\n"
            "  SUM(T1.LineTotal) AS cogs,\n"
            "  (SELECT SUM(OnHand * AvgPrice) FROM OITM WHERE validFor = 'Y') AS current_inventory_value,\n"
            "  SUM(T1.LineTotal)\n"
            "    / NULLIF((SELECT SUM(OnHand * AvgPrice) FROM OITM WHERE validFor = 'Y'), 0) AS turnover_ratio\n"
            "FROM OINV T0\n"
            "JOIN INV1 T1 ON T0.DocEntry = T1.DocEntry\n"
            "WHERE T0.DocDate BETWEEN :date_from AND :date_to\n"
            "  AND T0.CANCELLED = 'N'"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date", "required": True, "description": "Period start"},
            {"name": "date_to",   "type": "date", "required": True, "description": "Period end"},
        ],
        "output_schema": {"columns": [
            {"name": "cogs",                      "type": "number"},
            {"name": "current_inventory_value",   "type": "number"},
            {"name": "turnover_ratio",            "type": "number"},
        ]},
    },
    {
        "name": "item_movement_history",
        "description": "Inventory movements for a specific item.",
        "category": "filter",
        "domain": "inventory",
        "sql_template": (
            "SELECT T0.DocDate, T0.TransType, T0.ItemCode,\n"
            "       T0.Warehouse, T0.InQty, T0.OutQty, T0.Balance\n"
            "FROM OINM T0\n"
            "WHERE T0.ItemCode = :item_code\n"
            "  AND T0.DocDate BETWEEN :date_from AND :date_to\n"
            "ORDER BY T0.DocDate ASC, T0.DocEntry ASC"
        ),
        "input_schema": [
            {"name": "item_code", "type": "string", "required": True,  "description": "Item code"},
            {"name": "date_from", "type": "date",   "required": True,  "description": "Start date"},
            {"name": "date_to",   "type": "date",   "required": True,  "description": "End date"},
        ],
        "output_schema": {"columns": [
            {"name": "DocDate",   "type": "date"},
            {"name": "TransType", "type": "string"},
            {"name": "InQty",     "type": "number"},
            {"name": "OutQty",    "type": "number"},
            {"name": "Balance",   "type": "number"},
        ]},
    },
    {
        "name": "top_selling_items",
        "description": "Top N items by invoice quantity sold.",
        "category": "aggregate",
        "domain": "inventory",
        "sql_template": (
            "SELECT TOP :limit\n"
            "       T1.ItemCode, T1.Dscription AS item_name,\n"
            "       SUM(T1.Quantity) AS total_qty_sold,\n"
            "       SUM(T1.LineTotal) AS total_revenue\n"
            "FROM OINV T0\n"
            "JOIN INV1 T1 ON T0.DocEntry = T1.DocEntry\n"
            "WHERE T0.DocDate BETWEEN :date_from AND :date_to\n"
            "  AND T0.CANCELLED = 'N'\n"
            "GROUP BY T1.ItemCode, T1.Dscription\n"
            "ORDER BY total_qty_sold DESC"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date",    "required": True,  "description": "Start date"},
            {"name": "date_to",   "type": "date",    "required": True,  "description": "End date"},
            {"name": "limit",     "type": "integer", "required": False, "default": 10, "description": "Top N"},
        ],
        "output_schema": {"columns": [
            {"name": "ItemCode",       "type": "string"},
            {"name": "item_name",      "type": "string"},
            {"name": "total_qty_sold", "type": "number"},
            {"name": "total_revenue",  "type": "number"},
        ]},
    },
    {
        "name": "warehouse_stock_summary",
        "description": "Stock totals per warehouse.",
        "category": "aggregate",
        "domain": "inventory",
        "sql_template": (
            "SELECT T1.WhsCode, T2.WhsName,\n"
            "       COUNT(DISTINCT T1.ItemCode) AS item_count,\n"
            "       SUM(T1.OnHand) AS total_on_hand,\n"
            "       SUM(T1.OnHand * T0.AvgPrice) AS inventory_value\n"
            "FROM OITM T0\n"
            "JOIN OITW T1 ON T0.ItemCode = T1.ItemCode\n"
            "JOIN OWHS T2 ON T1.WhsCode = T2.WhsCode\n"
            "WHERE T0.validFor = 'Y'\n"
            "GROUP BY T1.WhsCode, T2.WhsName\n"
            "ORDER BY inventory_value DESC"
        ),
        "input_schema": [],
        "output_schema": {"columns": [
            {"name": "WhsCode",         "type": "string"},
            {"name": "WhsName",         "type": "string"},
            {"name": "item_count",      "type": "integer"},
            {"name": "total_on_hand",   "type": "number"},
            {"name": "inventory_value", "type": "number"},
        ]},
    },

    # ────────────────────────────────────────────────────────
    # OPERATIONS / PRODUCTION
    # ────────────────────────────────────────────────────────
    {
        "name": "production_order_summary",
        "description": "Production orders (OWOR) for a date range by status.",
        "category": "aggregate",
        "domain": "operations",
        "sql_template": (
            "SELECT Status,\n"
            "       COUNT(*) AS order_count,\n"
            "       SUM(PlannedQty) AS planned_qty,\n"
            "       SUM(CmpltQty) AS completed_qty\n"
            "FROM OWOR\n"
            "WHERE DocDate BETWEEN :date_from AND :date_to\n"
            "GROUP BY Status\n"
            "ORDER BY Status"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date", "required": True, "description": "Start date"},
            {"name": "date_to",   "type": "date", "required": True, "description": "End date"},
        ],
        "output_schema": {"columns": [
            {"name": "Status",        "type": "string"},
            {"name": "order_count",   "type": "integer"},
            {"name": "planned_qty",   "type": "number"},
            {"name": "completed_qty", "type": "number"},
        ]},
    },
    {
        "name": "production_efficiency",
        "description": "Production completion rate (completed / planned qty).",
        "category": "kpi",
        "domain": "operations",
        "sql_template": (
            "SELECT\n"
            "  SUM(PlannedQty) AS total_planned,\n"
            "  SUM(CmpltQty) AS total_completed,\n"
            "  CAST(SUM(CmpltQty) AS FLOAT) / NULLIF(SUM(PlannedQty), 0) * 100 AS completion_pct\n"
            "FROM OWOR\n"
            "WHERE DocDate BETWEEN :date_from AND :date_to\n"
            "  AND Status IN ('R', 'L')"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date", "required": True, "description": "Start date"},
            {"name": "date_to",   "type": "date", "required": True, "description": "End date"},
        ],
        "output_schema": {"columns": [
            {"name": "total_planned",   "type": "number"},
            {"name": "total_completed", "type": "number"},
            {"name": "completion_pct",  "type": "number"},
        ]},
    },
    {
        "name": "open_production_orders",
        "description": "Released production orders not yet closed.",
        "category": "entity_summary",
        "domain": "operations",
        "sql_template": (
            "SELECT DocNum, ItemCode, PlannedQty, CmpltQty,\n"
            "       PlannedQty - CmpltQty AS remaining_qty,\n"
            "       DueDate, Status\n"
            "FROM OWOR\n"
            "WHERE Status = 'R'\n"
            "  AND DueDate <= :as_of_date\n"
            "ORDER BY DueDate ASC"
        ),
        "input_schema": [
            {"name": "as_of_date", "type": "date", "required": True, "description": "As-of date"},
        ],
        "output_schema": {"columns": [
            {"name": "DocNum",        "type": "string"},
            {"name": "ItemCode",      "type": "string"},
            {"name": "remaining_qty", "type": "number"},
            {"name": "DueDate",       "type": "date"},
        ]},
    },

    # ────────────────────────────────────────────────────────
    # CRM / BUSINESS PARTNER
    # ────────────────────────────────────────────────────────
    {
        "name": "business_partner_detail",
        "description": "Master record and financial summary for a business partner.",
        "category": "filter",
        "domain": "sales",
        "sql_template": (
            "SELECT T0.CardCode, T0.CardName, T0.CardType,\n"
            "       T0.CntctPrsn, T0.Phone1, T0.E_Mail,\n"
            "       T0.Balance, T0.CreditLine,\n"
            "       T0.Currency, T0.GroupCode, T0.Territory\n"
            "FROM OCRD T0\n"
            "WHERE T0.CardCode = :card_code"
        ),
        "input_schema": [
            {"name": "card_code", "type": "string", "required": True, "description": "Business partner code"},
        ],
        "output_schema": {"columns": [
            {"name": "CardCode",  "type": "string"},
            {"name": "CardName",  "type": "string"},
            {"name": "CardType",  "type": "string"},
            {"name": "Balance",   "type": "number"},
            {"name": "E_Mail",    "type": "string"},
        ]},
    },
    {
        "name": "customer_360",
        "description": "360° customer view: invoices, payments, open orders, and balance.",
        "category": "join",
        "domain": "sales",
        "sql_template": (
            "SELECT\n"
            "  T0.CardCode, T0.CardName, T0.Balance AS current_balance,\n"
            "  (SELECT COUNT(*) FROM OINV WHERE CardCode = T0.CardCode AND CANCELLED='N') AS total_invoices,\n"
            "  (SELECT SUM(DocTotal) FROM OINV WHERE CardCode = T0.CardCode AND CANCELLED='N') AS lifetime_revenue,\n"
            "  (SELECT COUNT(*) FROM ORDR WHERE CardCode = T0.CardCode AND DocStatus='O' AND CANCELLED='N') AS open_orders\n"
            "FROM OCRD T0\n"
            "WHERE T0.CardCode = :card_code\n"
            "  AND T0.CardType = 'C'"
        ),
        "input_schema": [
            {"name": "card_code", "type": "string", "required": True, "description": "Customer code"},
        ],
        "output_schema": {"columns": [
            {"name": "CardCode",        "type": "string"},
            {"name": "CardName",        "type": "string"},
            {"name": "current_balance", "type": "number"},
            {"name": "total_invoices",  "type": "integer"},
            {"name": "lifetime_revenue","type": "number"},
            {"name": "open_orders",     "type": "integer"},
        ]},
    },
    {
        "name": "new_customers_count",
        "description": "Number of new customers created in a date range.",
        "category": "aggregate",
        "domain": "sales",
        "sql_template": (
            "SELECT COUNT(*) AS new_customer_count\n"
            "FROM OCRD\n"
            "WHERE CardType = 'C'\n"
            "  AND CreateDate BETWEEN :date_from AND :date_to"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date", "required": True, "description": "Start date"},
            {"name": "date_to",   "type": "date", "required": True, "description": "End date"},
        ],
        "output_schema": {"columns": [
            {"name": "new_customer_count", "type": "integer"},
        ]},
    },
    {
        "name": "service_call_summary",
        "description": "Service calls (OSCL) by status for a date range.",
        "category": "aggregate",
        "domain": "operations",
        "sql_template": (
            "SELECT Status, Priority,\n"
            "       COUNT(*) AS call_count\n"
            "FROM OSCL\n"
            "WHERE CreateDate BETWEEN :date_from AND :date_to\n"
            "GROUP BY Status, Priority\n"
            "ORDER BY Priority"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date", "required": True, "description": "Start date"},
            {"name": "date_to",   "type": "date", "required": True, "description": "End date"},
        ],
        "output_schema": {"columns": [
            {"name": "Status",     "type": "string"},
            {"name": "Priority",   "type": "string"},
            {"name": "call_count", "type": "integer"},
        ]},
    },

    # ────────────────────────────────────────────────────────
    # PAYROLL / HR
    # ────────────────────────────────────────────────────────
    {
        "name": "employee_headcount",
        "description": "Current employee headcount by department.",
        "category": "aggregate",
        "domain": "operations",
        "sql_template": (
            "SELECT T1.DeptName AS department,\n"
            "       COUNT(*) AS employee_count\n"
            "FROM OHEM T0\n"
            "JOIN ODPT T1 ON T0.dept = T1.DeptCode\n"
            "WHERE T0.Active = 'Y'\n"
            "GROUP BY T1.DeptName\n"
            "ORDER BY T1.DeptName"
        ),
        "input_schema": [],
        "output_schema": {"columns": [
            {"name": "department",     "type": "string"},
            {"name": "employee_count", "type": "integer"},
        ]},
    },

    # ────────────────────────────────────────────────────────
    # CROSS-DOMAIN / KPI BUNDLES
    # ────────────────────────────────────────────────────────
    {
        "name": "cash_conversion_cycle",
        "description": "Cash Conversion Cycle (DIO + DSO - DPO) for a period.",
        "category": "kpi",
        "domain": "finance",
        "sql_template": (
            "SELECT\n"
            "  -- DSO\n"
            "  (SELECT (SUM(DocTotal - PaidToDate))\n"
            "            / NULLIF(SUM(DocTotal) / NULLIF(DATEDIFF(day, :date_from, :date_to), 0), 0)\n"
            "   FROM OINV WHERE DocDate BETWEEN :date_from AND :date_to AND CANCELLED='N') AS dso_days,\n"
            "  -- DPO\n"
            "  (SELECT (SUM(DocTotal - PaidToDate))\n"
            "            / NULLIF(SUM(DocTotal) / NULLIF(DATEDIFF(day, :date_from, :date_to), 0), 0)\n"
            "   FROM OPCH WHERE DocDate BETWEEN :date_from AND :date_to AND CANCELLED='N') AS dpo_days,\n"
            "  -- DIO\n"
            "  (SELECT (SUM(OnHand * AvgPrice))\n"
            "            / NULLIF((\n"
            "                SELECT SUM(LineTotal) / NULLIF(DATEDIFF(day, :date_from, :date_to), 0)\n"
            "                FROM INV1 T1\n"
            "                JOIN OINV T0 ON T0.DocEntry = T1.DocEntry\n"
            "                WHERE T0.DocDate BETWEEN :date_from AND :date_to AND T0.CANCELLED='N'\n"
            "            ), 0)\n"
            "   FROM OITM WHERE validFor='Y') AS dio_days"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date", "required": True, "description": "Period start"},
            {"name": "date_to",   "type": "date", "required": True, "description": "Period end"},
        ],
        "output_schema": {"columns": [
            {"name": "dso_days", "type": "number"},
            {"name": "dpo_days", "type": "number"},
            {"name": "dio_days", "type": "number"},
        ]},
    },
    {
        "name": "gross_profit_margin",
        "description": "Gross profit and gross margin percentage for a period.",
        "category": "kpi",
        "domain": "finance",
        "sql_template": (
            "SELECT\n"
            "  SUM(T0.DocTotal) AS revenue,\n"
            "  SUM(T1.LineTotal) AS cogs,\n"
            "  SUM(T0.DocTotal) - SUM(T1.LineTotal) AS gross_profit,\n"
            "  (SUM(T0.DocTotal) - SUM(T1.LineTotal))\n"
            "    / NULLIF(SUM(T0.DocTotal), 0) * 100 AS gross_margin_pct\n"
            "FROM OINV T0\n"
            "JOIN INV1 T1 ON T0.DocEntry = T1.DocEntry\n"
            "WHERE T0.DocDate BETWEEN :date_from AND :date_to\n"
            "  AND T0.CANCELLED = 'N'"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date", "required": True, "description": "Period start"},
            {"name": "date_to",   "type": "date", "required": True, "description": "Period end"},
        ],
        "output_schema": {"columns": [
            {"name": "revenue",          "type": "number"},
            {"name": "cogs",             "type": "number"},
            {"name": "gross_profit",     "type": "number"},
            {"name": "gross_margin_pct", "type": "number"},
        ]},
    },
    {
        "name": "working_capital",
        "description": "Working capital = AR balance + Inventory value - AP balance.",
        "category": "kpi",
        "domain": "finance",
        "sql_template": (
            "SELECT\n"
            "  (SELECT SUM(DocTotal - PaidToDate) FROM OINV WHERE CANCELLED='N') AS ar_balance,\n"
            "  (SELECT SUM(OnHand * AvgPrice) FROM OITM WHERE validFor='Y') AS inventory_value,\n"
            "  (SELECT SUM(DocTotal - PaidToDate) FROM OPCH WHERE CANCELLED='N') AS ap_balance,\n"
            "  (SELECT SUM(DocTotal - PaidToDate) FROM OINV WHERE CANCELLED='N')\n"
            "  + (SELECT SUM(OnHand * AvgPrice) FROM OITM WHERE validFor='Y')\n"
            "  - (SELECT SUM(DocTotal - PaidToDate) FROM OPCH WHERE CANCELLED='N') AS working_capital"
        ),
        "input_schema": [],
        "output_schema": {"columns": [
            {"name": "ar_balance",       "type": "number"},
            {"name": "inventory_value",  "type": "number"},
            {"name": "ap_balance",       "type": "number"},
            {"name": "working_capital",  "type": "number"},
        ]},
    },
    {
        "name": "payment_receipt_summary",
        "description": "Incoming payment receipts (ORCT) for a period.",
        "category": "aggregate",
        "domain": "finance",
        "sql_template": (
            "SELECT COUNT(*) AS receipt_count,\n"
            "       SUM(DocTotal) AS total_received\n"
            "FROM ORCT\n"
            "WHERE DocDate BETWEEN :date_from AND :date_to\n"
            "  AND CANCELLED = 'N'"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date", "required": True, "description": "Start date"},
            {"name": "date_to",   "type": "date", "required": True, "description": "End date"},
        ],
        "output_schema": {"columns": [
            {"name": "receipt_count",  "type": "integer"},
            {"name": "total_received", "type": "number"},
        ]},
    },
    {
        "name": "vendor_payment_summary",
        "description": "Outgoing vendor payments (OVPM) for a period.",
        "category": "aggregate",
        "domain": "purchasing",
        "sql_template": (
            "SELECT COUNT(*) AS payment_count,\n"
            "       SUM(DocTotal) AS total_paid\n"
            "FROM OVPM\n"
            "WHERE DocDate BETWEEN :date_from AND :date_to\n"
            "  AND CANCELLED = 'N'"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date", "required": True, "description": "Start date"},
            {"name": "date_to",   "type": "date", "required": True, "description": "End date"},
        ],
        "output_schema": {"columns": [
            {"name": "payment_count", "type": "integer"},
            {"name": "total_paid",    "type": "number"},
        ]},
    },
    {
        "name": "budget_vs_actual",
        "description": "Budget vs actual comparison for a G/L account.",
        "category": "kpi",
        "domain": "finance",
        "sql_template": (
            "SELECT\n"
            "  T0.AcctCode,\n"
            "  SUM(T1.Debit) - SUM(T1.Credit) AS actual_amount,\n"
            "  (SELECT ISNULL(SUM(T2.Debit), 0)\n"
            "   FROM BGT1 T2\n"
            "   JOIN OBGT T3 ON T2.AbsId = T3.AbsId\n"
            "   WHERE T2.AcctCode = T0.AcctCode\n"
            "     AND T3.Active = 'Y'\n"
            "     AND T3.BgtYear = YEAR(:date_from)) AS budget_amount\n"
            "FROM OACT T0\n"
            "JOIN JDT1 T1 ON T0.AcctCode = T1.Account\n"
            "JOIN OJDT T4 ON T1.TransId = T4.TransId\n"
            "WHERE T0.AcctCode = :account_code\n"
            "  AND T4.RefDate BETWEEN :date_from AND :date_to\n"
            "GROUP BY T0.AcctCode"
        ),
        "input_schema": [
            {"name": "account_code", "type": "string", "required": True, "description": "G/L account code"},
            {"name": "date_from",    "type": "date",   "required": True, "description": "Period start"},
            {"name": "date_to",      "type": "date",   "required": True, "description": "Period end"},
        ],
        "output_schema": {"columns": [
            {"name": "AcctCode",       "type": "string"},
            {"name": "actual_amount",  "type": "number"},
            {"name": "budget_amount",  "type": "number"},
        ]},
    },
    {
        "name": "sales_target_vs_actual",
        "description": "Salesperson quota vs actual invoice revenue.",
        "category": "kpi",
        "domain": "sales",
        "sql_template": (
            "SELECT T0.SlpCode, T0.SlpName,\n"
            "       T0.Memo AS quota_info,\n"
            "       SUM(T1.DocTotal) AS actual_revenue\n"
            "FROM OSLP T0\n"
            "LEFT JOIN OINV T1 ON T0.SlpCode = T1.SlpCode\n"
            "  AND T1.DocDate BETWEEN :date_from AND :date_to\n"
            "  AND T1.CANCELLED = 'N'\n"
            "GROUP BY T0.SlpCode, T0.SlpName, T0.Memo\n"
            "ORDER BY actual_revenue DESC"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date", "required": True, "description": "Period start"},
            {"name": "date_to",   "type": "date", "required": True, "description": "Period end"},
        ],
        "output_schema": {"columns": [
            {"name": "SlpCode",         "type": "string"},
            {"name": "SlpName",         "type": "string"},
            {"name": "actual_revenue",  "type": "number"},
        ]},
    },
    {
        "name": "purchase_price_variance",
        "description": "Variance between PO price and actual GRPO price per item.",
        "category": "kpi",
        "domain": "purchasing",
        "sql_template": (
            "SELECT\n"
            "  T2.ItemCode, T2.Dscription AS item_name,\n"
            "  AVG(T2.Price) AS avg_po_price,\n"
            "  AVG(T4.Price) AS avg_grpo_price,\n"
            "  AVG(T4.Price) - AVG(T2.Price) AS price_variance\n"
            "FROM OPOR T1\n"
            "JOIN POR1 T2 ON T1.DocEntry = T2.DocEntry\n"
            "LEFT JOIN OPDN T3 ON T1.DocNum = T3.BsDocNum\n"
            "LEFT JOIN PDN1 T4 ON T3.DocEntry = T4.DocEntry AND T2.ItemCode = T4.ItemCode\n"
            "WHERE T1.DocDate BETWEEN :date_from AND :date_to\n"
            "  AND T1.CANCELLED = 'N'\n"
            "GROUP BY T2.ItemCode, T2.Dscription\n"
            "ORDER BY ABS(price_variance) DESC"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date", "required": True, "description": "Period start"},
            {"name": "date_to",   "type": "date", "required": True, "description": "Period end"},
        ],
        "output_schema": {"columns": [
            {"name": "ItemCode",        "type": "string"},
            {"name": "item_name",       "type": "string"},
            {"name": "avg_po_price",    "type": "number"},
            {"name": "avg_grpo_price",  "type": "number"},
            {"name": "price_variance",  "type": "number"},
        ]},
    },
    {
        "name": "on_time_delivery_rate",
        "description": "Percentage of sales deliveries made on or before the due date.",
        "category": "kpi",
        "domain": "operations",
        "sql_template": (
            "SELECT\n"
            "  COUNT(*) AS total_deliveries,\n"
            "  SUM(CASE WHEN DocDate <= DocDueDate THEN 1 ELSE 0 END) AS on_time_count,\n"
            "  CAST(SUM(CASE WHEN DocDate <= DocDueDate THEN 1 ELSE 0 END) AS FLOAT)\n"
            "    / NULLIF(COUNT(*), 0) * 100 AS on_time_pct\n"
            "FROM ODLN\n"
            "WHERE DocDate BETWEEN :date_from AND :date_to\n"
            "  AND CANCELLED = 'N'"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date", "required": True, "description": "Period start"},
            {"name": "date_to",   "type": "date", "required": True, "description": "Period end"},
        ],
        "output_schema": {"columns": [
            {"name": "total_deliveries", "type": "integer"},
            {"name": "on_time_count",    "type": "integer"},
            {"name": "on_time_pct",      "type": "number"},
        ]},
    },
    {
        "name": "item_profitability",
        "description": "Gross profit per item from AR invoices.",
        "category": "aggregate",
        "domain": "sales",
        "sql_template": (
            "SELECT\n"
            "  T1.ItemCode, T1.Dscription AS item_name,\n"
            "  SUM(T1.LineTotal) AS revenue,\n"
            "  SUM(T1.GrossBuyPr * T1.Quantity) AS cogs,\n"
            "  SUM(T1.LineTotal) - SUM(T1.GrossBuyPr * T1.Quantity) AS gross_profit,\n"
            "  (SUM(T1.LineTotal) - SUM(T1.GrossBuyPr * T1.Quantity))\n"
            "    / NULLIF(SUM(T1.LineTotal), 0) * 100 AS margin_pct\n"
            "FROM OINV T0\n"
            "JOIN INV1 T1 ON T0.DocEntry = T1.DocEntry\n"
            "WHERE T0.DocDate BETWEEN :date_from AND :date_to\n"
            "  AND T0.CANCELLED = 'N'\n"
            "GROUP BY T1.ItemCode, T1.Dscription\n"
            "ORDER BY gross_profit DESC"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date", "required": True, "description": "Period start"},
            {"name": "date_to",   "type": "date", "required": True, "description": "Period end"},
        ],
        "output_schema": {"columns": [
            {"name": "ItemCode",     "type": "string"},
            {"name": "item_name",    "type": "string"},
            {"name": "revenue",      "type": "number"},
            {"name": "gross_profit", "type": "number"},
            {"name": "margin_pct",   "type": "number"},
        ]},
    },
    {
        "name": "credit_limit_utilization",
        "description": "Customer credit limit vs current balance utilization.",
        "category": "entity_summary",
        "domain": "sales",
        "sql_template": (
            "SELECT CardCode, CardName, CreditLine, Balance,\n"
            "       Balance / NULLIF(CreditLine, 0) * 100 AS utilization_pct\n"
            "FROM OCRD\n"
            "WHERE CardType = 'C'\n"
            "  AND CreditLine > 0\n"
            "  AND Balance / NULLIF(CreditLine, 0) >= :min_utilization_pct / 100.0\n"
            "ORDER BY utilization_pct DESC"
        ),
        "input_schema": [
            {"name": "min_utilization_pct", "type": "number", "required": False,
             "default": 70, "description": "Minimum utilization % to show (default 70)"},
        ],
        "output_schema": {"columns": [
            {"name": "CardCode",        "type": "string"},
            {"name": "CardName",        "type": "string"},
            {"name": "CreditLine",      "type": "number"},
            {"name": "Balance",         "type": "number"},
            {"name": "utilization_pct", "type": "number"},
        ]},
    },
    {
        "name": "stock_replenishment_candidates",
        "description": "Items suitable for replenishment based on reorder point and lead time.",
        "category": "entity_summary",
        "domain": "inventory",
        "sql_template": (
            "SELECT T0.ItemCode, T0.ItemName,\n"
            "       T1.WhsCode, T1.OnHand, T1.MinStock, T1.ReorderQty,\n"
            "       T0.LeadTime\n"
            "FROM OITM T0\n"
            "JOIN OITW T1 ON T0.ItemCode = T1.ItemCode\n"
            "WHERE T0.validFor = 'Y'\n"
            "  AND T0.PurchItem = 'Y'\n"
            "  AND T1.OnHand <= T1.MinStock\n"
            "  AND T1.ReorderQty > 0\n"
            "ORDER BY T1.OnHand ASC"
        ),
        "input_schema": [],
        "output_schema": {"columns": [
            {"name": "ItemCode",    "type": "string"},
            {"name": "ItemName",    "type": "string"},
            {"name": "WhsCode",     "type": "string"},
            {"name": "OnHand",      "type": "number"},
            {"name": "MinStock",    "type": "number"},
            {"name": "ReorderQty",  "type": "number"},
            {"name": "LeadTime",    "type": "integer"},
        ]},
    },
    {
        "name": "tax_report_summary",
        "description": "Sales and purchase tax totals by tax code for a period.",
        "category": "aggregate",
        "domain": "finance",
        "sql_template": (
            "SELECT T1.TaxCode, T2.TaxName,\n"
            "       SUM(CASE WHEN T0.ObjType = '13' THEN T1.TaxSum ELSE 0 END) AS sales_tax,\n"
            "       SUM(CASE WHEN T0.ObjType = '18' THEN T1.TaxSum ELSE 0 END) AS purchase_tax\n"
            "FROM OJDT T0\n"
            "JOIN JDT1 T1 ON T0.TransId = T1.TransId\n"
            "JOIN OSTC T2 ON T1.TaxCode = T2.Code\n"
            "WHERE T0.RefDate BETWEEN :date_from AND :date_to\n"
            "  AND T1.TaxCode IS NOT NULL\n"
            "GROUP BY T1.TaxCode, T2.TaxName\n"
            "ORDER BY T1.TaxCode"
        ),
        "input_schema": [
            {"name": "date_from", "type": "date", "required": True, "description": "Period start"},
            {"name": "date_to",   "type": "date", "required": True, "description": "Period end"},
        ],
        "output_schema": {"columns": [
            {"name": "TaxCode",       "type": "string"},
            {"name": "TaxName",       "type": "string"},
            {"name": "sales_tax",     "type": "number"},
            {"name": "purchase_tax",  "type": "number"},
        ]},
    },
    {
        "name": "price_list_by_item",
        "description": "Price list entries for a specific item across all price lists.",
        "category": "filter",
        "domain": "sales",
        "sql_template": (
            "SELECT T0.ListNum, T1.ListName, T0.ItemCode,\n"
            "       T0.Price, T0.Currency, T0.UomEntry\n"
            "FROM ITM1 T0\n"
            "JOIN OPLN T1 ON T0.ListNum = T1.ListNum\n"
            "WHERE T0.ItemCode = :item_code\n"
            "ORDER BY T0.ListNum"
        ),
        "input_schema": [
            {"name": "item_code", "type": "string", "required": True, "description": "Item code"},
        ],
        "output_schema": {"columns": [
            {"name": "ListName", "type": "string"},
            {"name": "Price",    "type": "number"},
            {"name": "Currency", "type": "string"},
        ]},
    },
    {
        "name": "bank_reconciliation_summary",
        "description": "Bank account balance vs cleared transactions for reconciliation.",
        "category": "kpi",
        "domain": "finance",
        "sql_template": (
            "SELECT T0.AcctCode, T0.AcctName,\n"
            "       T0.CurrTotal AS bank_balance,\n"
            "       SUM(CASE WHEN T1.Reconcile = 'Y' THEN T1.Debit - T1.Credit ELSE 0 END) AS cleared_balance,\n"
            "       T0.CurrTotal\n"
            "         - SUM(CASE WHEN T1.Reconcile = 'Y' THEN T1.Debit - T1.Credit ELSE 0 END) AS unreconciled\n"
            "FROM OACT T0\n"
            "JOIN JDT1 T1 ON T0.AcctCode = T1.Account\n"
            "WHERE T0.AcctCode = :account_code\n"
            "  AND T1.RefDate <= :as_of_date\n"
            "GROUP BY T0.AcctCode, T0.AcctName, T0.CurrTotal"
        ),
        "input_schema": [
            {"name": "account_code", "type": "string", "required": True, "description": "Bank account G/L code"},
            {"name": "as_of_date",   "type": "date",   "required": True, "description": "As-of date"},
        ],
        "output_schema": {"columns": [
            {"name": "AcctCode",        "type": "string"},
            {"name": "bank_balance",    "type": "number"},
            {"name": "cleared_balance", "type": "number"},
            {"name": "unreconciled",    "type": "number"},
        ]},
    },
]


def get_tool(name: str) -> dict | None:
    """Case-insensitive lookup by tool name."""
    target = name.lower()
    return next((t for t in SAP_B1_TOOLS if t["name"].lower() == target), None)


def get_tools_by_domain(domain: str) -> list[dict]:
    return [t for t in SAP_B1_TOOLS if t["domain"] == domain]


def get_tools_by_category(category: str) -> list[dict]:
    return [t for t in SAP_B1_TOOLS if t["category"] == category]
