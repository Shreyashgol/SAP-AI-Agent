"""
MSSQL schema fingerprinting — identifies ERP schema patterns and selects
the best matching entity pack (SAP B1, Dynamics BC, Sage 300, or AI fallback).

Detection uses table-name pattern matching with confidence scoring (SL-011).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.metadata import MetadataTable

log = get_logger(__name__)


# ── Signature patterns per ERP ─────────────────────────────────────────────────

# Each signature is a list of (pattern, weight) tuples.
# The pattern is a substring match against table names (case-insensitive).

_SIGNATURES: dict[str, list[tuple[str, float]]] = {
    "sap_b1": [
        ("OCRD", 2.0),   # Business Partners
        ("OINV", 2.0),   # AR Invoices
        ("ORDR", 2.0),   # Sales Orders
        ("OITM", 2.0),   # Items
        ("OJDT", 1.5),   # Journal Entries
        ("OPCH", 1.5),   # AP Invoices
        ("ORCT", 1.5),   # Incoming Payments
        ("OSLP", 1.0),   # Sales Employees
        ("OWHS", 1.0),   # Warehouses
        ("INV1", 1.0),   # Invoice Lines
        ("RDR1", 1.0),   # Sales Order Lines
        ("OCPR", 0.5),   # Contact Persons
    ],
    "dynamics_bc": [
        ("$General Ledger Entry",   2.0),
        ("$Customer Ledger Entry",  2.0),
        ("$Vendor Ledger Entry",    2.0),
        ("$Sales Header",           1.5),
        ("$Purchase Header",        1.5),
        ("$Item Ledger Entry",      1.5),
        ("$Item",                   1.0),
        ("$Customer",               1.0),
        ("$Vendor",                 1.0),
        ("$G/L Account",            1.0),
        ("$Resource",               0.5),
        ("$Job Ledger Entry",       0.5),
    ],
    "sage_300": [
        ("ARBL",   2.0),   # AR Balance
        ("APBL",   2.0),   # AP Balance
        ("OEORD",  2.0),   # OE Order Header
        ("POPORL", 2.0),   # PO Order
        ("ICITEM", 1.5),   # IC Item
        ("ICWHSE", 1.0),   # IC Warehouse
        ("GLBCTL", 1.5),   # GL Batch
        ("ARCS",   1.0),   # AR Customer
        ("APVD",   1.0),   # AP Vendor
    ],
    "generic_erp": [
        ("invoice",      0.5),
        ("order",        0.5),
        ("customer",     0.5),
        ("vendor",       0.5),
        ("item",         0.5),
        ("payment",      0.5),
        ("journal",      0.5),
        ("ledger",       0.5),
        ("warehouse",    0.5),
        ("employee",     0.5),
    ],
}

_CONFIDENCE_THRESHOLD = 0.4


@dataclass
class FingerprintResult:
    detected_erp: str  # sap_b1 | dynamics_bc | sage_300 | generic_erp | unknown
    confidence: float
    matched_patterns: list[str]
    pack_source: str   # sap_b1 | mssql_dynamics | mssql_sage | ai_generated


async def fingerprint_connection(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    connection_id: uuid.UUID,
    schema_name: str | None = None,
) -> FingerprintResult:
    """
    Scan the crawled table names for a connection and score against known ERP signatures.
    Returns the best match and confidence.
    """
    q = select(MetadataTable.table_name).where(
        MetadataTable.tenant_id == tenant_id,
        MetadataTable.connection_id == connection_id,
        MetadataTable.is_system_table.is_(False),
    )
    if schema_name:
        q = q.where(MetadataTable.schema_name == schema_name)

    result = await db.execute(q)
    table_names = [r[0] for r in result.fetchall()]

    if not table_names:
        return FingerprintResult(
            detected_erp="unknown",
            confidence=0.0,
            matched_patterns=[],
            pack_source="ai_generated",
        )

    scores: dict[str, float] = {}
    matched: dict[str, list[str]] = {}

    for erp, patterns in _SIGNATURES.items():
        score = 0.0
        hits: list[str] = []
        for pattern, weight in patterns:
            pat_lower = pattern.lower()
            for tbl in table_names:
                if pat_lower in tbl.lower():
                    score += weight
                    hits.append(f"{pattern} → {tbl}")
                    break  # count pattern once
        max_possible = sum(w for _, w in patterns)
        scores[erp] = score / max_possible if max_possible else 0.0
        matched[erp] = hits

    best_erp = max(scores, key=lambda k: scores[k])
    best_confidence = scores[best_erp]

    if best_confidence < _CONFIDENCE_THRESHOLD:
        best_erp = "unknown"
        pack_source = "ai_generated"
    elif best_erp == "sap_b1":
        pack_source = "sap_b1"
    elif best_erp == "dynamics_bc":
        pack_source = "mssql_dynamics"
    elif best_erp == "sage_300":
        pack_source = "mssql_sage"
    else:
        pack_source = "ai_generated"

    log.info(
        "mssql_fingerprint.result",
        connection_id=str(connection_id),
        detected_erp=best_erp,
        confidence=round(best_confidence, 3),
        pack_source=pack_source,
    )

    return FingerprintResult(
        detected_erp=best_erp,
        confidence=best_confidence,
        matched_patterns=matched.get(best_erp, []),
        pack_source=pack_source,
    )
