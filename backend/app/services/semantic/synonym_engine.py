"""
Synonym engine — resolves business terms to canonical entity/metric names.
Seeds a default synonym library for SAP B1 terminology (SL-006).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.semantic import SynonymMapping

# ── Default synonym seeds ──────────────────────────────────────────────────────
# Format: (synonym, canonical_term, entity_type)
# entity_type: metric | entity | attribute

_DEFAULT_SYNONYMS: list[tuple[str, str, str]] = [
    # Revenue / sales
    ("revenue",           "Total Revenue",           "metric"),
    ("sales",             "Total Revenue",           "metric"),
    ("turnover",          "Total Revenue",           "metric"),
    ("net sales",         "Total Revenue",           "metric"),
    ("income",            "Total Revenue",           "metric"),
    ("bookings",          "Sales Order Value",       "metric"),
    ("orders",            "Total Sales Orders",      "metric"),
    ("order value",       "Sales Order Value",       "metric"),

    # Cost / spend
    ("cost of goods sold","Total Purchases",         "metric"),
    ("cogs",              "Total Purchases",         "metric"),
    ("spend",             "Total Purchases",         "metric"),
    ("procurement",       "Total Purchases",         "metric"),
    ("expenses",          "Total Expenses",          "metric"),

    # Profit
    ("profit",            "Gross Profit",            "metric"),
    ("gross profit",      "Gross Profit",            "metric"),
    ("margin",            "Gross Margin %",          "metric"),
    ("gross margin",      "Gross Margin %",          "metric"),

    # Receivables / payables
    ("ar",                "Accounts Receivable Balance", "metric"),
    ("receivables",       "Accounts Receivable Balance", "metric"),
    ("debtors",           "Accounts Receivable Balance", "metric"),
    ("ap",                "Accounts Payable Balance",    "metric"),
    ("payables",          "Accounts Payable Balance",    "metric"),
    ("creditors",         "Accounts Payable Balance",    "metric"),
    ("overdue",           "Overdue Receivables",         "metric"),
    ("outstanding invoices","Overdue Receivables",       "metric"),

    # Inventory
    ("stock",             "Stock On Hand",           "metric"),
    ("inventory",         "Total Stock Value",       "metric"),
    ("stock value",       "Total Stock Value",       "metric"),
    ("on hand",           "Stock On Hand",           "metric"),

    # KPI shortcuts
    ("dso",               "Days Sales Outstanding (DSO)", "metric"),
    ("dpo",               "Days Payable Outstanding (DPO)", "metric"),
    ("dio",               "Days Inventory Outstanding (DIO)", "metric"),
    ("ccc",               "Cash Conversion Cycle",    "metric"),
    ("working capital",   "Working Capital",          "metric"),

    # Entity synonyms
    ("customer",          "Business Partner",        "entity"),
    ("client",            "Business Partner",        "entity"),
    ("vendor",            "Business Partner",        "entity"),
    ("supplier",          "Business Partner",        "entity"),
    ("partner",           "Business Partner",        "entity"),
    ("item",              "Item Master",             "entity"),
    ("product",           "Item Master",             "entity"),
    ("article",           "Item Master",             "entity"),
    ("sku",               "Item Master",             "entity"),
    ("invoice",           "Sales Invoice",           "entity"),
    ("sales invoice",     "Sales Invoice",           "entity"),
    ("ar invoice",        "Sales Invoice",           "entity"),
    ("bill",              "Purchase Invoice",        "entity"),
    ("ap invoice",        "Purchase Invoice",        "entity"),
    ("purchase invoice",  "Purchase Invoice",        "entity"),
    ("po",                "Purchase Order",          "entity"),
    ("purchase order",    "Purchase Order",          "entity"),
    ("so",                "Sales Order",             "entity"),
    ("sales order",       "Sales Order",             "entity"),
    ("warehouse",         "Warehouse",               "entity"),
    ("whs",               "Warehouse",               "entity"),
    ("credit note",       "Credit Memo (Sales)",     "entity"),
    ("credit memo",       "Credit Memo (Sales)",     "entity"),
    ("delivery",          "Delivery Note",           "entity"),
    ("do",                "Delivery Note",           "entity"),
    ("production order",  "Production Order",        "entity"),
    ("work order",        "Production Order",        "entity"),
    ("wo",                "Production Order",        "entity"),
    ("journal",           "Journal Entry",           "entity"),
    ("gl account",        "G/L Account",             "entity"),
    ("account",           "G/L Account",             "entity"),
    ("employee",          "Employee",                "entity"),
    ("staff",             "Employee",                "entity"),
    ("quote",             "Sales Quotation",         "entity"),
    ("quotation",         "Sales Quotation",         "entity"),

    # Attribute synonyms
    ("amount",            "DocTotal",                "attribute"),
    ("value",             "DocTotal",                "attribute"),
    ("total",             "DocTotal",                "attribute"),
    ("date",              "DocDate",                 "attribute"),
    ("posting date",      "DocDate",                 "attribute"),
    ("due date",          "DocDueDate",              "attribute"),
    ("status",            "DocStatus",               "attribute"),
    ("quantity",          "Quantity",                "attribute"),
    ("qty",               "Quantity",                "attribute"),
    ("unit price",        "Price",                   "attribute"),
    ("price",             "Price",                   "attribute"),
    ("description",       "Dscription",              "attribute"),
    ("name",              "CardName",                "attribute"),
]


class SynonymEngine:
    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self._cache: dict[tuple[str, str], str] | None = None

    async def resolve(self, term: str, entity_type: str | None = None) -> str | None:
        """Return canonical term for synonym, or None if not found."""
        await self._ensure_cache()
        key = (term.lower().strip(), entity_type or "")
        # Try exact type match first, then any type
        if key in self._cache:  # type: ignore[operator]
            return self._cache[key]  # type: ignore[index]
        for et in ("metric", "entity", "attribute", ""):
            alt_key = (term.lower().strip(), et)
            if alt_key in self._cache:  # type: ignore[operator]
                return self._cache[alt_key]  # type: ignore[index]
        return None

    async def _ensure_cache(self) -> None:
        if self._cache is not None:
            return
        result = await self.db.execute(
            select(SynonymMapping).where(
                SynonymMapping.tenant_id == self.tenant_id
            )
        )
        self._cache = {
            (r.synonym.lower(), r.entity_type): r.canonical_term
            for r in result.scalars().all()
        }

    def invalidate_cache(self) -> None:
        self._cache = None


async def seed_synonyms(db: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Seed default SAP B1 synonyms for a tenant. Skips existing entries."""
    result = await db.execute(
        select(SynonymMapping.synonym).where(
            SynonymMapping.tenant_id == tenant_id
        )
    )
    existing = {r[0].lower() for r in result.fetchall()}

    inserted = 0
    for synonym, canonical, entity_type in _DEFAULT_SYNONYMS:
        if synonym.lower() in existing:
            continue
        db.add(SynonymMapping(
            tenant_id=tenant_id,
            synonym=synonym,
            canonical_term=canonical,
            entity_type=entity_type,
        ))
        inserted += 1

    await db.flush()
    return inserted
