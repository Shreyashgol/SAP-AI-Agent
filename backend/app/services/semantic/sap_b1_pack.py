"""
SAP Business One Entity Pack — canonical table/attribute/rule mappings.

Covers 80+ SAP B1 HANA tables across all 5 business domains.
Each entry maps a raw table to a business entity with:
  - entity_name: human-readable business name
  - domain:      finance | sales | purchasing | inventory | operations
  - description: what the table represents
  - attributes:  column → {display_name, semantic_type, description}
  - rules:       list of always-applied SQL predicates (SL-007)
  - status_codes: optional {column → {code → label}} reference data (SL-010)

semantic_type values:
  currency | date | quantity | code | text | boolean | percentage | id | datetime
"""

from __future__ import annotations

from typing import TypedDict


class AttributeMapping(TypedDict, total=False):
    display_name: str
    semantic_type: str
    description: str


class BusinessRuleEntry(TypedDict):
    rule_name: str
    predicate_sql: str
    description: str
    is_default: bool


class EntityPackEntry(TypedDict, total=False):
    entity_name: str
    domain: str
    description: str
    attributes: dict[str, AttributeMapping]
    rules: list[BusinessRuleEntry]
    status_codes: dict[str, dict[str, str]]


# ── SAP B1 Pack ────────────────────────────────────────────────────────────────

SAP_B1_PACK: dict[str, EntityPackEntry] = {

    # ── BUSINESS PARTNERS ─────────────────────────────────────────────────────
    "OCRD": {
        "entity_name": "Business Partner",
        "domain": "sales",
        "description": "Master record for all customers, vendors, and leads.",
        "attributes": {
            "CardCode":   {"display_name": "Partner Code",      "semantic_type": "id",       "description": "Unique business partner identifier"},
            "CardName":   {"display_name": "Partner Name",      "semantic_type": "text",     "description": "Full name of the business partner"},
            "CardType":   {"display_name": "Partner Type",      "semantic_type": "code",     "description": "C=Customer, S=Supplier, L=Lead"},
            "Balance":    {"display_name": "Account Balance",   "semantic_type": "currency", "description": "Current open balance in system currency"},
            "CreditLine": {"display_name": "Credit Limit",      "semantic_type": "currency", "description": "Maximum allowed credit"},
            "Phone1":     {"display_name": "Primary Phone",     "semantic_type": "text",     "description": "Main contact phone number"},
            "E_Mail":     {"display_name": "Email Address",     "semantic_type": "text",     "description": "Primary email address"},
            "Country":    {"display_name": "Country",           "semantic_type": "code",     "description": "ISO country code"},
            "GroupCode":  {"display_name": "Partner Group",     "semantic_type": "id",       "description": "FK to OCRG — partner group classification"},
            "Territory":  {"display_name": "Sales Territory",   "semantic_type": "id",       "description": "Assigned sales territory code"},
            "SalesPerso": {"display_name": "Sales Person",      "semantic_type": "id",       "description": "Assigned sales person ID"},
            "Froze":      {"display_name": "Is Frozen",         "semantic_type": "boolean",  "description": "Y=partner is frozen (no new transactions)"},
            "validFor":   {"display_name": "Is Active",         "semantic_type": "boolean",  "description": "Y=active partner"},
            "CreateDate": {"display_name": "Created Date",      "semantic_type": "date",     "description": "Date the partner record was created"},
            "UpdateDate": {"display_name": "Last Updated",      "semantic_type": "date",     "description": "Date of last modification"},
        },
        "rules": [
            {
                "rule_name": "active_partners_only",
                "predicate_sql": "\"validFor\" = 'Y' AND \"Froze\" = 'N'",
                "description": "Exclude frozen and inactive partners from analytics",
                "is_default": True,
            }
        ],
        "status_codes": {
            "CardType": {"C": "Customer", "S": "Supplier", "L": "Lead"},
            "Froze":    {"Y": "Frozen", "N": "Active"},
        },
    },

    # ── SALES ─────────────────────────────────────────────────────────────────
    "ORDR": {
        "entity_name": "Sales Order",
        "domain": "sales",
        "description": "Sales order headers — confirmed customer orders.",
        "attributes": {
            "DocNum":     {"display_name": "Order Number",       "semantic_type": "id",       "description": "User-visible document number"},
            "CardCode":   {"display_name": "Customer Code",      "semantic_type": "id",       "description": "FK to OCRD"},
            "CardName":   {"display_name": "Customer Name",      "semantic_type": "text"},
            "DocDate":    {"display_name": "Order Date",         "semantic_type": "date",     "description": "Date the order was placed"},
            "DocDueDate": {"display_name": "Delivery Due Date",  "semantic_type": "date"},
            "DocTotal":   {"display_name": "Order Total",        "semantic_type": "currency", "description": "Total order value including tax"},
            "DocTotalSy": {"display_name": "Order Total (Sys)",  "semantic_type": "currency", "description": "Total in system base currency"},
            "DocStatus":  {"display_name": "Order Status",       "semantic_type": "code"},
            "Cancelled":  {"display_name": "Is Cancelled",       "semantic_type": "boolean"},
            "SlpCode":    {"display_name": "Sales Person",       "semantic_type": "id"},
            "TrnspCode":  {"display_name": "Shipping Method",    "semantic_type": "id"},
            "Comments":   {"display_name": "Remarks",            "semantic_type": "text"},
        },
        "rules": [
            {
                "rule_name": "open_sales_orders",
                "predicate_sql": "\"DocStatus\" = 'O' AND \"Cancelled\" = 'N'",
                "description": "Only open, non-cancelled orders",
                "is_default": True,
            }
        ],
        "status_codes": {
            "DocStatus": {"O": "Open", "C": "Closed"},
            "Cancelled": {"Y": "Cancelled", "N": "Active"},
        },
    },

    "RDR1": {
        "entity_name": "Sales Order Line",
        "domain": "sales",
        "description": "Line items of sales orders.",
        "attributes": {
            "DocEntry":   {"display_name": "Order Entry ID",     "semantic_type": "id"},
            "ItemCode":   {"display_name": "Item Code",          "semantic_type": "id",       "description": "FK to OITM"},
            "Dscription": {"display_name": "Item Description",   "semantic_type": "text"},
            "Quantity":   {"display_name": "Ordered Quantity",   "semantic_type": "quantity"},
            "OpenQty":    {"display_name": "Open Quantity",      "semantic_type": "quantity"},
            "Price":      {"display_name": "Unit Price",         "semantic_type": "currency"},
            "LineTotal":  {"display_name": "Line Total",         "semantic_type": "currency"},
            "WhsCode":    {"display_name": "Warehouse",          "semantic_type": "id"},
            "ShipDate":   {"display_name": "Promised Ship Date", "semantic_type": "date"},
        },
        "rules": [],
    },

    "OINV": {
        "entity_name": "Sales Invoice",
        "domain": "finance",
        "description": "A/R invoices — posted customer billing documents.",
        "attributes": {
            "DocNum":     {"display_name": "Invoice Number",     "semantic_type": "id"},
            "CardCode":   {"display_name": "Customer Code",      "semantic_type": "id"},
            "CardName":   {"display_name": "Customer Name",      "semantic_type": "text"},
            "DocDate":    {"display_name": "Invoice Date",       "semantic_type": "date"},
            "DocDueDate": {"display_name": "Due Date",           "semantic_type": "date"},
            "DocTotal":   {"display_name": "Invoice Total",      "semantic_type": "currency"},
            "PaidToDate": {"display_name": "Paid Amount",        "semantic_type": "currency"},
            "DocStatus":  {"display_name": "Invoice Status",     "semantic_type": "code"},
            "Cancelled":  {"display_name": "Is Cancelled",       "semantic_type": "boolean"},
            "VatSum":     {"display_name": "Tax Amount",         "semantic_type": "currency"},
            "DiscSum":    {"display_name": "Discount Amount",    "semantic_type": "currency"},
            "SlpCode":    {"display_name": "Sales Person",       "semantic_type": "id"},
        },
        "rules": [
            {
                "rule_name": "posted_invoices",
                "predicate_sql": "\"Cancelled\" = 'N'",
                "description": "Exclude cancelled invoices from revenue analysis",
                "is_default": True,
            }
        ],
        "status_codes": {
            "DocStatus": {"O": "Open", "C": "Closed/Paid"},
        },
    },

    "INV1": {
        "entity_name": "Sales Invoice Line",
        "domain": "finance",
        "description": "Line items on A/R sales invoices.",
        "attributes": {
            "DocEntry":   {"display_name": "Invoice Entry ID",   "semantic_type": "id"},
            "ItemCode":   {"display_name": "Item Code",          "semantic_type": "id"},
            "Dscription": {"display_name": "Description",        "semantic_type": "text"},
            "Quantity":   {"display_name": "Quantity",           "semantic_type": "quantity"},
            "Price":      {"display_name": "Unit Price",         "semantic_type": "currency"},
            "LineTotal":  {"display_name": "Line Total",         "semantic_type": "currency"},
            "GrossBuyPr": {"display_name": "Cost Price",        "semantic_type": "currency"},
            "WhsCode":    {"display_name": "Warehouse",          "semantic_type": "id"},
            "AcctCode":   {"display_name": "Revenue Account",    "semantic_type": "id"},
        },
        "rules": [],
    },

    "ORIN": {
        "entity_name": "Credit Memo (Sales)",
        "domain": "finance",
        "description": "A/R credit memos — reversals and credits issued to customers.",
        "attributes": {
            "DocNum":     {"display_name": "Credit Memo Number", "semantic_type": "id"},
            "CardCode":   {"display_name": "Customer Code",      "semantic_type": "id"},
            "DocDate":    {"display_name": "Credit Date",        "semantic_type": "date"},
            "DocTotal":   {"display_name": "Credit Total",       "semantic_type": "currency"},
            "DocStatus":  {"display_name": "Status",             "semantic_type": "code"},
            "Cancelled":  {"display_name": "Is Cancelled",       "semantic_type": "boolean"},
        },
        "rules": [{"rule_name": "posted_credit_memos", "predicate_sql": "\"Cancelled\" = 'N'",
                   "description": "Exclude cancelled credit memos", "is_default": True}],
    },

    # ── PURCHASING ────────────────────────────────────────────────────────────
    "OPOR": {
        "entity_name": "Purchase Order",
        "domain": "purchasing",
        "description": "Purchase orders issued to vendors.",
        "attributes": {
            "DocNum":     {"display_name": "PO Number",          "semantic_type": "id"},
            "CardCode":   {"display_name": "Vendor Code",        "semantic_type": "id"},
            "CardName":   {"display_name": "Vendor Name",        "semantic_type": "text"},
            "DocDate":    {"display_name": "PO Date",            "semantic_type": "date"},
            "DocDueDate": {"display_name": "Delivery Due Date",  "semantic_type": "date"},
            "DocTotal":   {"display_name": "PO Total",           "semantic_type": "currency"},
            "DocStatus":  {"display_name": "PO Status",          "semantic_type": "code"},
            "Cancelled":  {"display_name": "Is Cancelled",       "semantic_type": "boolean"},
        },
        "rules": [
            {"rule_name": "open_purchase_orders", "predicate_sql": "\"DocStatus\" = 'O' AND \"Cancelled\" = 'N'",
             "description": "Open non-cancelled POs", "is_default": True}
        ],
        "status_codes": {"DocStatus": {"O": "Open", "C": "Closed"}},
    },

    "POR1": {
        "entity_name": "Purchase Order Line",
        "domain": "purchasing",
        "description": "Line items on purchase orders.",
        "attributes": {
            "DocEntry":   {"display_name": "PO Entry ID",        "semantic_type": "id"},
            "ItemCode":   {"display_name": "Item Code",          "semantic_type": "id"},
            "Dscription": {"display_name": "Description",        "semantic_type": "text"},
            "Quantity":   {"display_name": "Ordered Quantity",   "semantic_type": "quantity"},
            "OpenQty":    {"display_name": "Open Quantity",      "semantic_type": "quantity"},
            "Price":      {"display_name": "Unit Price",         "semantic_type": "currency"},
            "LineTotal":  {"display_name": "Line Total",         "semantic_type": "currency"},
            "WhsCode":    {"display_name": "Warehouse",          "semantic_type": "id"},
        },
        "rules": [],
    },

    "OPCH": {
        "entity_name": "Purchase Invoice",
        "domain": "purchasing",
        "description": "A/P invoices — vendor bills.",
        "attributes": {
            "DocNum":     {"display_name": "AP Invoice Number",  "semantic_type": "id"},
            "CardCode":   {"display_name": "Vendor Code",        "semantic_type": "id"},
            "CardName":   {"display_name": "Vendor Name",        "semantic_type": "text"},
            "DocDate":    {"display_name": "Invoice Date",       "semantic_type": "date"},
            "DocDueDate": {"display_name": "Due Date",           "semantic_type": "date"},
            "DocTotal":   {"display_name": "Invoice Total",      "semantic_type": "currency"},
            "PaidToDate": {"display_name": "Paid Amount",        "semantic_type": "currency"},
            "DocStatus":  {"display_name": "Status",             "semantic_type": "code"},
            "Cancelled":  {"display_name": "Is Cancelled",       "semantic_type": "boolean"},
            "VatSum":     {"display_name": "Tax Amount",         "semantic_type": "currency"},
        },
        "rules": [{"rule_name": "posted_ap_invoices", "predicate_sql": "\"Cancelled\" = 'N'",
                   "description": "Exclude cancelled AP invoices", "is_default": True}],
    },

    "PCH1": {
        "entity_name": "Purchase Invoice Line",
        "domain": "purchasing",
        "description": "Line items on A/P invoices.",
        "attributes": {
            "DocEntry":   {"display_name": "AP Invoice Entry ID", "semantic_type": "id"},
            "ItemCode":   {"display_name": "Item Code",           "semantic_type": "id"},
            "Dscription": {"display_name": "Description",         "semantic_type": "text"},
            "Quantity":   {"display_name": "Quantity",            "semantic_type": "quantity"},
            "Price":      {"display_name": "Unit Price",          "semantic_type": "currency"},
            "LineTotal":  {"display_name": "Line Total",          "semantic_type": "currency"},
            "AcctCode":   {"display_name": "Expense Account",     "semantic_type": "id"},
        },
        "rules": [],
    },

    "ORPC": {
        "entity_name": "Credit Memo (Purchase)",
        "domain": "purchasing",
        "description": "A/P credit memos — returns to vendors.",
        "attributes": {
            "DocNum":     {"display_name": "AP Credit Memo Number", "semantic_type": "id"},
            "CardCode":   {"display_name": "Vendor Code",           "semantic_type": "id"},
            "DocDate":    {"display_name": "Credit Date",           "semantic_type": "date"},
            "DocTotal":   {"display_name": "Credit Total",          "semantic_type": "currency"},
            "DocStatus":  {"display_name": "Status",                "semantic_type": "code"},
            "Cancelled":  {"display_name": "Is Cancelled",          "semantic_type": "boolean"},
        },
        "rules": [{"rule_name": "posted_ap_credits", "predicate_sql": "\"Cancelled\" = 'N'",
                   "description": "Exclude cancelled AP credits", "is_default": True}],
    },

    "OGRPO": {
        "entity_name": "Goods Receipt PO",
        "domain": "purchasing",
        "description": "Goods receipt against a purchase order.",
        "attributes": {
            "DocNum":     {"display_name": "GR-PO Number",       "semantic_type": "id"},
            "CardCode":   {"display_name": "Vendor Code",        "semantic_type": "id"},
            "DocDate":    {"display_name": "Receipt Date",       "semantic_type": "date"},
            "DocTotal":   {"display_name": "Total Value",        "semantic_type": "currency"},
            "DocStatus":  {"display_name": "Status",             "semantic_type": "code"},
            "Cancelled":  {"display_name": "Is Cancelled",       "semantic_type": "boolean"},
        },
        "rules": [{"rule_name": "posted_grpos", "predicate_sql": "\"Cancelled\" = 'N'",
                   "description": "Exclude cancelled GRPOs", "is_default": True}],
    },

    # ── INVENTORY ─────────────────────────────────────────────────────────────
    "OITM": {
        "entity_name": "Item Master",
        "domain": "inventory",
        "description": "Product / item master data.",
        "attributes": {
            "ItemCode":   {"display_name": "Item Code",          "semantic_type": "id"},
            "ItemName":   {"display_name": "Item Name",          "semantic_type": "text"},
            "ItmsGrpCod": {"display_name": "Item Group",         "semantic_type": "id",       "description": "FK to OITB"},
            "InvntryUom": {"display_name": "Inventory UoM",      "semantic_type": "code"},
            "OnHand":     {"display_name": "Qty On Hand",        "semantic_type": "quantity"},
            "IsCommited": {"display_name": "Qty Committed",      "semantic_type": "quantity"},
            "OnOrder":    {"display_name": "Qty On Order",       "semantic_type": "quantity"},
            "AvgPrice":   {"display_name": "Average Cost",       "semantic_type": "currency"},
            "LastPurPrc": {"display_name": "Last Purchase Price","semantic_type": "currency"},
            "PrchseItem": {"display_name": "Is Purchased",       "semantic_type": "boolean"},
            "SellItem":   {"display_name": "Is Sold",            "semantic_type": "boolean"},
            "InvntItem":  {"display_name": "Is Inventoried",     "semantic_type": "boolean"},
            "validFor":   {"display_name": "Is Active",          "semantic_type": "boolean"},
            "Series":     {"display_name": "Numbering Series",   "semantic_type": "id"},
        },
        "rules": [
            {
                "rule_name": "active_items",
                "predicate_sql": "\"validFor\" = 'Y'",
                "description": "Exclude discontinued / inactive items",
                "is_default": True,
            }
        ],
    },

    "OITB": {
        "entity_name": "Item Group",
        "domain": "inventory",
        "description": "Item group / category master.",
        "attributes": {
            "ItmsGrpCod": {"display_name": "Group Code",         "semantic_type": "id"},
            "ItmsGrpNam": {"display_name": "Group Name",         "semantic_type": "text"},
        },
        "rules": [],
    },

    "OITW": {
        "entity_name": "Item Warehouse Stock",
        "domain": "inventory",
        "description": "On-hand stock per item per warehouse.",
        "attributes": {
            "ItemCode":   {"display_name": "Item Code",          "semantic_type": "id"},
            "WhsCode":    {"display_name": "Warehouse Code",     "semantic_type": "id"},
            "OnHand":     {"display_name": "Qty On Hand",        "semantic_type": "quantity"},
            "IsCommited": {"display_name": "Qty Committed",      "semantic_type": "quantity"},
            "OnOrder":    {"display_name": "Qty On Order",       "semantic_type": "quantity"},
            "AvgPrice":   {"display_name": "Average Cost",       "semantic_type": "currency"},
        },
        "rules": [],
    },

    "OWHS": {
        "entity_name": "Warehouse",
        "domain": "inventory",
        "description": "Warehouse master data.",
        "attributes": {
            "WhsCode":    {"display_name": "Warehouse Code",     "semantic_type": "id"},
            "WhsName":    {"display_name": "Warehouse Name",     "semantic_type": "text"},
            "Location":   {"display_name": "Location",           "semantic_type": "text"},
            "Inactive":   {"display_name": "Is Inactive",        "semantic_type": "boolean"},
        },
        "rules": [],
    },

    "OIGE": {
        "entity_name": "Goods Receipt",
        "domain": "inventory",
        "description": "Goods receipts not linked to a PO.",
        "attributes": {
            "DocNum":     {"display_name": "GR Number",          "semantic_type": "id"},
            "DocDate":    {"display_name": "Receipt Date",       "semantic_type": "date"},
            "DocTotal":   {"display_name": "Total Value",        "semantic_type": "currency"},
            "Cancelled":  {"display_name": "Is Cancelled",       "semantic_type": "boolean"},
        },
        "rules": [{"rule_name": "posted_grs", "predicate_sql": "\"Cancelled\" = 'N'",
                   "description": "Exclude cancelled goods receipts", "is_default": True}],
    },

    "OIGD": {
        "entity_name": "Goods Issue",
        "domain": "inventory",
        "description": "Goods issues — material consumed or released.",
        "attributes": {
            "DocNum":     {"display_name": "GI Number",          "semantic_type": "id"},
            "DocDate":    {"display_name": "Issue Date",         "semantic_type": "date"},
            "DocTotal":   {"display_name": "Total Value",        "semantic_type": "currency"},
            "Cancelled":  {"display_name": "Is Cancelled",       "semantic_type": "boolean"},
        },
        "rules": [{"rule_name": "posted_gis", "predicate_sql": "\"Cancelled\" = 'N'",
                   "description": "Exclude cancelled goods issues", "is_default": True}],
    },

    "OWTR": {
        "entity_name": "Inventory Transfer",
        "domain": "inventory",
        "description": "Stock transfers between warehouses.",
        "attributes": {
            "DocNum":     {"display_name": "Transfer Number",    "semantic_type": "id"},
            "DocDate":    {"display_name": "Transfer Date",      "semantic_type": "date"},
            "FromWhsCod": {"display_name": "From Warehouse",     "semantic_type": "id"},
            "ToWhsCod":   {"display_name": "To Warehouse",       "semantic_type": "id"},
            "Cancelled":  {"display_name": "Is Cancelled",       "semantic_type": "boolean"},
        },
        "rules": [],
    },

    "OITL": {
        "entity_name": "Item Ledger Entry",
        "domain": "inventory",
        "description": "All inventory postings and movements.",
        "attributes": {
            "ItemCode":   {"display_name": "Item Code",          "semantic_type": "id"},
            "DocDate":    {"display_name": "Posting Date",       "semantic_type": "date"},
            "TransType":  {"display_name": "Transaction Type",   "semantic_type": "code"},
            "Quantity":   {"display_name": "Quantity",           "semantic_type": "quantity"},
            "Price":      {"display_name": "Unit Cost",          "semantic_type": "currency"},
            "WhsCode":    {"display_name": "Warehouse",          "semantic_type": "id"},
        },
        "rules": [],
    },

    "OBTN": {
        "entity_name": "Batch Number",
        "domain": "inventory",
        "description": "Batch / lot tracking master data.",
        "attributes": {
            "ItemCode":   {"display_name": "Item Code",          "semantic_type": "id"},
            "BatchNum":   {"display_name": "Batch Number",       "semantic_type": "id"},
            "ExpDate":    {"display_name": "Expiry Date",        "semantic_type": "date"},
            "MnfDate":    {"display_name": "Manufacture Date",   "semantic_type": "date"},
            "Quantity":   {"display_name": "Current Quantity",   "semantic_type": "quantity"},
        },
        "rules": [],
    },

    # ── FINANCE ───────────────────────────────────────────────────────────────
    "OJDT": {
        "entity_name": "Journal Entry",
        "domain": "finance",
        "description": "General ledger journal entry headers.",
        "attributes": {
            "TransId":    {"display_name": "Transaction ID",     "semantic_type": "id"},
            "RefDate":    {"display_name": "Posting Date",       "semantic_type": "date"},
            "DueDate":    {"display_name": "Due Date",           "semantic_type": "date"},
            "Memo":       {"display_name": "Memo",               "semantic_type": "text"},
            "TransType":  {"display_name": "Source Type",        "semantic_type": "code"},
            "BaseRef":    {"display_name": "Source Document Ref","semantic_type": "id"},
        },
        "rules": [],
    },

    "JDT1": {
        "entity_name": "Journal Entry Line",
        "domain": "finance",
        "description": "Individual debit/credit lines within a journal entry.",
        "attributes": {
            "TransId":    {"display_name": "Transaction ID",     "semantic_type": "id"},
            "Account":    {"display_name": "G/L Account",        "semantic_type": "id"},
            "Debit":      {"display_name": "Debit Amount",       "semantic_type": "currency"},
            "Credit":     {"display_name": "Credit Amount",      "semantic_type": "currency"},
            "SYSDebit":   {"display_name": "Debit (Sys)",        "semantic_type": "currency"},
            "SYSCredit":  {"display_name": "Credit (Sys)",       "semantic_type": "currency"},
            "FCDebit":    {"display_name": "Debit (Foreign)",    "semantic_type": "currency"},
            "FCCredit":   {"display_name": "Credit (Foreign)",   "semantic_type": "currency"},
            "ShortName":  {"display_name": "Business Partner",   "semantic_type": "id"},
            "ContraAct":  {"display_name": "Contra Account",     "semantic_type": "id"},
            "ProfitCode": {"display_name": "Cost Center",        "semantic_type": "id"},
        },
        "rules": [],
    },

    "OACT": {
        "entity_name": "G/L Account",
        "domain": "finance",
        "description": "Chart of accounts — general ledger account master.",
        "attributes": {
            "AcctCode":   {"display_name": "Account Code",       "semantic_type": "id"},
            "AcctName":   {"display_name": "Account Name",       "semantic_type": "text"},
            "ActType":    {"display_name": "Account Type",       "semantic_type": "code"},
            "Balance":    {"display_name": "Current Balance",    "semantic_type": "currency"},
            "Finanse":    {"display_name": "Is P&L Account",     "semantic_type": "boolean"},
            "Locked":     {"display_name": "Is Locked",          "semantic_type": "boolean"},
            "validFor":   {"display_name": "Is Active",          "semantic_type": "boolean"},
        },
        "rules": [
            {"rule_name": "active_gl_accounts", "predicate_sql": "\"validFor\" = 'Y' AND \"Locked\" = 'N'",
             "description": "Active, unlocked accounts only", "is_default": False}
        ],
        "status_codes": {
            "ActType": {"A": "Assets", "L": "Liabilities", "E": "Equity",
                        "R": "Revenue", "X": "Expenses", "O": "Other"},
        },
    },

    "OCST": {
        "entity_name": "Cost Center",
        "domain": "finance",
        "description": "Profit centres / cost centres for dimension reporting.",
        "attributes": {
            "PrcCode":    {"display_name": "Cost Center Code",   "semantic_type": "id"},
            "PrcName":    {"display_name": "Cost Center Name",   "semantic_type": "text"},
            "DimCode":    {"display_name": "Dimension",          "semantic_type": "id"},
            "ValidFrom":  {"display_name": "Valid From",         "semantic_type": "date"},
            "ValidTo":    {"display_name": "Valid To",           "semantic_type": "date"},
        },
        "rules": [],
    },

    "OIVL": {
        "entity_name": "Inventory Valuation",
        "domain": "finance",
        "description": "Inventory value movements per posting.",
        "attributes": {
            "ItemCode":   {"display_name": "Item Code",          "semantic_type": "id"},
            "DocDate":    {"display_name": "Posting Date",       "semantic_type": "date"},
            "TransType":  {"display_name": "Transaction Type",   "semantic_type": "code"},
            "InQty":      {"display_name": "In Quantity",        "semantic_type": "quantity"},
            "OutQty":     {"display_name": "Out Quantity",       "semantic_type": "quantity"},
            "Price":      {"display_name": "Unit Value",         "semantic_type": "currency"},
            "Amount":     {"display_name": "Total Amount",       "semantic_type": "currency"},
            "WhsCode":    {"display_name": "Warehouse",          "semantic_type": "id"},
        },
        "rules": [],
    },

    "ODUN": {
        "entity_name": "Dunning Letter",
        "domain": "finance",
        "description": "Overdue payment dunning letters sent to customers.",
        "attributes": {
            "CardCode":   {"display_name": "Customer Code",      "semantic_type": "id"},
            "DunDate":    {"display_name": "Dunning Date",       "semantic_type": "date"},
            "DunLevel":   {"display_name": "Dunning Level",      "semantic_type": "quantity"},
        },
        "rules": [],
    },

    # ── PRICING ───────────────────────────────────────────────────────────────
    "OPLN": {
        "entity_name": "Price List",
        "domain": "sales",
        "description": "Price list master — groups item prices by list.",
        "attributes": {
            "ListNum":    {"display_name": "Price List Number",  "semantic_type": "id"},
            "ListName":   {"display_name": "Price List Name",    "semantic_type": "text"},
            "validFor":   {"display_name": "Is Active",          "semantic_type": "boolean"},
        },
        "rules": [],
    },

    "ITM1": {
        "entity_name": "Item Price",
        "domain": "sales",
        "description": "Item price per price list.",
        "attributes": {
            "ItemCode":   {"display_name": "Item Code",          "semantic_type": "id"},
            "PriceList":  {"display_name": "Price List",         "semantic_type": "id"},
            "Price":      {"display_name": "Unit Price",         "semantic_type": "currency"},
            "Currency":   {"display_name": "Currency",           "semantic_type": "code"},
        },
        "rules": [],
    },

    # ── PAYMENTS ──────────────────────────────────────────────────────────────
    "ORCT": {
        "entity_name": "Incoming Payment",
        "domain": "finance",
        "description": "Customer payment receipts (A/R).",
        "attributes": {
            "DocNum":     {"display_name": "Payment Number",     "semantic_type": "id"},
            "CardCode":   {"display_name": "Customer Code",      "semantic_type": "id"},
            "DocDate":    {"display_name": "Payment Date",       "semantic_type": "date"},
            "DocTotal":   {"display_name": "Payment Amount",     "semantic_type": "currency"},
            "Cancelled":  {"display_name": "Is Cancelled",       "semantic_type": "boolean"},
        },
        "rules": [{"rule_name": "posted_receipts", "predicate_sql": "\"Cancelled\" = 'N'",
                   "description": "Exclude cancelled receipts", "is_default": True}],
    },

    "OVPM": {
        "entity_name": "Outgoing Payment",
        "domain": "finance",
        "description": "Vendor payment runs (A/P).",
        "attributes": {
            "DocNum":     {"display_name": "Payment Number",     "semantic_type": "id"},
            "CardCode":   {"display_name": "Vendor Code",        "semantic_type": "id"},
            "DocDate":    {"display_name": "Payment Date",       "semantic_type": "date"},
            "DocTotal":   {"display_name": "Payment Amount",     "semantic_type": "currency"},
            "Cancelled":  {"display_name": "Is Cancelled",       "semantic_type": "boolean"},
        },
        "rules": [{"rule_name": "posted_payments", "predicate_sql": "\"Cancelled\" = 'N'",
                   "description": "Exclude cancelled payments", "is_default": True}],
    },

    # ── OPERATIONS ────────────────────────────────────────────────────────────
    "OWOR": {
        "entity_name": "Production Order",
        "domain": "operations",
        "description": "Manufacturing / work orders.",
        "attributes": {
            "DocNum":     {"display_name": "Order Number",       "semantic_type": "id"},
            "ItemCode":   {"display_name": "Finished Good",      "semantic_type": "id"},
            "PlannedQty": {"display_name": "Planned Quantity",   "semantic_type": "quantity"},
            "CmpltQty":   {"display_name": "Completed Quantity", "semantic_type": "quantity"},
            "RjctQty":    {"display_name": "Rejected Quantity",  "semantic_type": "quantity"},
            "StartDate":  {"display_name": "Start Date",         "semantic_type": "date"},
            "DueDate":    {"display_name": "Due Date",           "semantic_type": "date"},
            "Status":     {"display_name": "Status",             "semantic_type": "code"},
            "Cancelled":  {"display_name": "Is Cancelled",       "semantic_type": "boolean"},
        },
        "rules": [{"rule_name": "active_work_orders", "predicate_sql": "\"Cancelled\" = 'N'",
                   "description": "Exclude cancelled work orders", "is_default": True}],
        "status_codes": {
            "Status": {"P": "Planned", "R": "Released", "C": "Closed"},
        },
    },

    "OQUO": {
        "entity_name": "Sales Quotation",
        "domain": "sales",
        "description": "Sales quotations sent to prospects and customers.",
        "attributes": {
            "DocNum":     {"display_name": "Quotation Number",   "semantic_type": "id"},
            "CardCode":   {"display_name": "Customer Code",      "semantic_type": "id"},
            "DocDate":    {"display_name": "Quote Date",         "semantic_type": "date"},
            "DocDueDate": {"display_name": "Valid Until",        "semantic_type": "date"},
            "DocTotal":   {"display_name": "Quote Total",        "semantic_type": "currency"},
            "DocStatus":  {"display_name": "Status",             "semantic_type": "code"},
            "Cancelled":  {"display_name": "Is Cancelled",       "semantic_type": "boolean"},
        },
        "rules": [{"rule_name": "open_quotations", "predicate_sql": "\"DocStatus\" = 'O' AND \"Cancelled\" = 'N'",
                   "description": "Open non-cancelled quotations", "is_default": True}],
    },

    "ODLN": {
        "entity_name": "Delivery Note",
        "domain": "sales",
        "description": "Outbound delivery notes — goods shipped to customers.",
        "attributes": {
            "DocNum":     {"display_name": "Delivery Number",    "semantic_type": "id"},
            "CardCode":   {"display_name": "Customer Code",      "semantic_type": "id"},
            "DocDate":    {"display_name": "Delivery Date",      "semantic_type": "date"},
            "DocTotal":   {"display_name": "Delivery Value",     "semantic_type": "currency"},
            "DocStatus":  {"display_name": "Status",             "semantic_type": "code"},
            "Cancelled":  {"display_name": "Is Cancelled",       "semantic_type": "boolean"},
        },
        "rules": [{"rule_name": "posted_deliveries", "predicate_sql": "\"Cancelled\" = 'N'",
                   "description": "Exclude cancelled deliveries", "is_default": True}],
    },

    "ORDN": {
        "entity_name": "Return (Sales)",
        "domain": "sales",
        "description": "Customer returns — goods returned by customers.",
        "attributes": {
            "DocNum":     {"display_name": "Return Number",      "semantic_type": "id"},
            "CardCode":   {"display_name": "Customer Code",      "semantic_type": "id"},
            "DocDate":    {"display_name": "Return Date",        "semantic_type": "date"},
            "DocTotal":   {"display_name": "Return Value",       "semantic_type": "currency"},
            "Cancelled":  {"display_name": "Is Cancelled",       "semantic_type": "boolean"},
        },
        "rules": [],
    },

    "OPDN": {
        "entity_name": "Purchase Delivery",
        "domain": "purchasing",
        "description": "Vendor-side delivery notes.",
        "attributes": {
            "DocNum":     {"display_name": "PD Number",          "semantic_type": "id"},
            "CardCode":   {"display_name": "Vendor Code",        "semantic_type": "id"},
            "DocDate":    {"display_name": "Delivery Date",      "semantic_type": "date"},
            "DocTotal":   {"display_name": "Delivery Value",     "semantic_type": "currency"},
            "Cancelled":  {"display_name": "Is Cancelled",       "semantic_type": "boolean"},
        },
        "rules": [{"rule_name": "posted_purchase_deliveries", "predicate_sql": "\"Cancelled\" = 'N'",
                   "description": "Exclude cancelled purchase deliveries", "is_default": True}],
    },

    # ── HR ────────────────────────────────────────────────────────────────────
    "OHEM": {
        "entity_name": "Employee",
        "domain": "operations",
        "description": "HR employee master data.",
        "attributes": {
            "empID":      {"display_name": "Employee ID",        "semantic_type": "id"},
            "firstName":  {"display_name": "First Name",         "semantic_type": "text"},
            "lastName":   {"display_name": "Last Name",          "semantic_type": "text"},
            "Department": {"display_name": "Department",         "semantic_type": "id"},
            "Position":   {"display_name": "Position",           "semantic_type": "text"},
            "startDate":  {"display_name": "Start Date",         "semantic_type": "date"},
            "Active":     {"display_name": "Is Active",          "semantic_type": "boolean"},
            "Manager":    {"display_name": "Manager",            "semantic_type": "id"},
            "Branch":     {"display_name": "Branch",             "semantic_type": "id"},
        },
        "rules": [
            {"rule_name": "active_employees", "predicate_sql": "\"Active\" = 'Y'",
             "description": "Active employees only", "is_default": True}
        ],
    },

    # ── MASTER / LOOKUP TABLES ────────────────────────────────────────────────
    "OUSR": {
        "entity_name": "System User",
        "domain": "operations",
        "description": "SAP B1 system user accounts.",
        "attributes": {
            "USERID":     {"display_name": "User ID",            "semantic_type": "id"},
            "U_NAME":     {"display_name": "Username",           "semantic_type": "text"},
            "USER_CODE":  {"display_name": "User Code",          "semantic_type": "id"},
            "U_Password": {"display_name": "Password Hash",      "semantic_type": "text"},
            "Superuser":  {"display_name": "Is Superuser",       "semantic_type": "boolean"},
        },
        "rules": [],
    },

    "OCRG": {
        "entity_name": "Business Partner Group",
        "domain": "sales",
        "description": "Grouping categories for business partners.",
        "attributes": {
            "GroupCode": {"display_name": "Group Code",          "semantic_type": "id"},
            "GroupName": {"display_name": "Group Name",          "semantic_type": "text"},
        },
        "rules": [],
    },

    "OMRC": {
        "entity_name": "Item Category",
        "domain": "inventory",
        "description": "Secondary item classification (manufacturer / category).",
        "attributes": {
            "FirmCode":   {"display_name": "Category Code",      "semantic_type": "id"},
            "FirmName":   {"display_name": "Category Name",      "semantic_type": "text"},
        },
        "rules": [],
    },

    "OSLP": {
        "entity_name": "Sales Person",
        "domain": "sales",
        "description": "Sales employee (salesperson) master.",
        "attributes": {
            "SlpCode":    {"display_name": "Sales Person Code",  "semantic_type": "id"},
            "SlpName":    {"display_name": "Sales Person Name",  "semantic_type": "text"},
            "Active":     {"display_name": "Is Active",          "semantic_type": "boolean"},
        },
        "rules": [],
    },

    "OCUR": {
        "entity_name": "Currency",
        "domain": "finance",
        "description": "Currency master — all currencies supported by the system.",
        "attributes": {
            "CurrCode":   {"display_name": "Currency Code",      "semantic_type": "id"},
            "CurrName":   {"display_name": "Currency Name",      "semantic_type": "text"},
            "Symbol":     {"display_name": "Symbol",             "semantic_type": "text"},
        },
        "rules": [],
    },

    "ORTT": {
        "entity_name": "Exchange Rate",
        "domain": "finance",
        "description": "Daily exchange rates per currency.",
        "attributes": {
            "Currency":   {"display_name": "Currency Code",      "semantic_type": "id"},
            "RateDate":   {"display_name": "Rate Date",          "semantic_type": "date"},
            "Rate":       {"display_name": "Exchange Rate",      "semantic_type": "currency"},
        },
        "rules": [],
    },

    "OWTQ": {
        "entity_name": "Inventory Transfer Request",
        "domain": "inventory",
        "description": "Requests for stock transfers between warehouses.",
        "attributes": {
            "DocNum":     {"display_name": "Request Number",     "semantic_type": "id"},
            "DocDate":    {"display_name": "Request Date",       "semantic_type": "date"},
            "FromWhsCod": {"display_name": "From Warehouse",     "semantic_type": "id"},
            "ToWhsCod":   {"display_name": "To Warehouse",       "semantic_type": "id"},
            "DocStatus":  {"display_name": "Status",             "semantic_type": "code"},
        },
        "rules": [{"rule_name": "open_transfer_requests",
                   "predicate_sql": "\"DocStatus\" = 'O'",
                   "description": "Open transfer requests only", "is_default": False}],
    },

    "OPRC": {
        "entity_name": "Cost Center Dimension",
        "domain": "finance",
        "description": "Cost center / profit center dimension master.",
        "attributes": {
            "PrcCode":    {"display_name": "Dimension Code",     "semantic_type": "id"},
            "PrcName":    {"display_name": "Dimension Name",     "semantic_type": "text"},
            "DimCode":    {"display_name": "Dimension Number",   "semantic_type": "id"},
        },
        "rules": [],
    },

    "OCOG": {
        "entity_name": "Company",
        "domain": "operations",
        "description": "Company data — the SAP B1 company record.",
        "attributes": {
            "CompnyName": {"display_name": "Company Name",       "semantic_type": "text"},
            "Country":    {"display_name": "Country",            "semantic_type": "code"},
            "Currency":   {"display_name": "Base Currency",      "semantic_type": "id"},
        },
        "rules": [],
    },
}


def get_pack_tables() -> list[str]:
    """Return all table names covered by the pack."""
    return list(SAP_B1_PACK.keys())


def get_entry(table_name: str) -> EntityPackEntry | None:
    return SAP_B1_PACK.get(table_name.upper())
