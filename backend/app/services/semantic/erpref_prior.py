"""
ERPRef prior — SAP Business One reference knowledge used to warm-start onboarding.

The enriched reference files in ``data/erpref_enriched_part*.json`` describe the
SAP B1 core tables: business names, descriptions, primary keys, and — most
usefully — the join graph that SAP B1 does NOT declare at the database level.
This module loads them once and applies them as a *prior* on top of a freshly
crawled catalog:

  • MetadataTable.ai_description  ← business_name + description    (fill-not-clobber)
  • MetadataColumn.ai_description ← column business_name/desc       (fill-not-clobber)
  • MetadataRelation rows         ← prior joins, but ONLY where both leg columns
                                    exist in the crawl (intersection) and the edge
                                    is new

It is strictly an annotation layer: it never creates a table or column, and every
downstream consumer (ai_mapper, ai_generator, runtime text_to_sql) keeps validating
generated SQL against the real catalog — so a wrong hint can only cause a tool to be
rejected, never bad SQL to ship.

The caller (the apply_erpref_prior task) is responsible for gating this on a SAP B1
fingerprint; this module unconditionally applies whatever the prior knows about the
tables that were actually crawled.
"""

from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.settings import get_settings
from app.models.metadata import MetadataColumn, MetadataRelation, MetadataTable

log = get_logger(__name__)
settings = get_settings()

# relation_type marker for prior-injected join edges (fits String(20)).
_PRIOR_RELATION_TYPE = "reference_prior"


# ── Loading (pure) ──────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_prior() -> dict[str, dict]:
    """Merge ``data/erpref_enriched_part*.json`` into ``{TABLE_NAME_UPPER: table}``.

    Cached for the process lifetime — the files are static reference data.
    """
    prior: dict[str, dict] = {}
    data_dir = Path(settings.erpref_data_dir)
    for path in sorted(data_dir.glob("erpref_enriched_part*.json")):
        try:
            tables = json.loads(path.read_text())
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("erpref_prior.load_error", file=str(path), error=str(exc))
            continue
        for t in tables or []:
            name = (t.get("table_name") or "").strip().upper()
            if name:
                prior[name] = t
    log.info("erpref_prior.loaded", tables=len(prior))
    return prior


# ── Extraction (pure, unit-testable without a DB) ───────────────────────────────

def table_description(t: dict) -> str | None:
    """Business name + description for a prior table, or None if neither exists."""
    bn = (t.get("business_name") or "").strip()
    desc = (t.get("description") or "").strip()
    if bn and desc:
        return f"{bn} — {desc}"
    return bn or desc or None


def column_descriptions(t: dict) -> dict[str, str]:
    """``{COLUMN_NAME_UPPER: description}`` for the columns the prior documents."""
    out: dict[str, str] = {}
    for c in t.get("columns", []) or []:
        field = (c.get("field") or "").strip()
        if not field:
            continue
        bn = (c.get("business_name") or "").strip()
        desc = (c.get("description") or "").strip()
        text = f"{bn} — {desc}" if bn and desc else (bn or desc)
        if text:
            out[field.upper()] = text
    return out


def join_edges(t: dict, columns_by_table: dict[str, set[str]]) -> list[dict]:
    """Intersection-filtered join edges for prior table ``t``.

    ``columns_by_table`` maps ``TABLE_UPPER -> {COLUMN_UPPER, ...}`` from the crawl.
    Only edges whose *both* legs (table + column) exist in the crawl are returned, so
    a join can never reference a table/column that wasn't actually discovered.
    """
    from_table = (t.get("table_name") or "").strip().upper()
    from_cols = columns_by_table.get(from_table)
    if not from_cols:
        return []
    edges: list[dict] = []
    for j in t.get("joins", []) or []:
        to_table = (j.get("to_table") or "").strip().upper()
        from_col = (j.get("from_column") or "").strip().upper()
        to_col = (j.get("to_column") or "").strip().upper()
        to_cols = columns_by_table.get(to_table)
        if not (to_table and from_col and to_col and to_cols):
            continue
        if from_col not in from_cols or to_col not in to_cols:
            continue
        edges.append({
            "from_table": from_table,
            "from_column": from_col,
            "to_table": to_table,
            "to_column": to_col,
            "confidence": float(j.get("confidence", 0.8)),
            "purpose": (j.get("purpose") or "").strip() or None,
        })
    return edges


# ── Application (DB-bound) ──────────────────────────────────────────────────────

class ErpRefPrior:
    """Applies the ERPRef prior to a connection's already-crawled catalog."""

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id

    async def apply(self, connection_id: uuid.UUID) -> dict[str, int]:
        empty = {"tables_annotated": 0, "columns_annotated": 0, "relations_added": 0}
        prior = load_prior()
        if not prior:
            return empty

        tables_res = await self.db.execute(
            select(MetadataTable).where(
                MetadataTable.tenant_id == self.tenant_id,
                MetadataTable.connection_id == connection_id,
                MetadataTable.is_system_table.is_(False),
            )
        )
        tables = list(tables_res.scalars().all())
        if not tables:
            return empty

        tbl_by_name = {t.table_name.upper(): t for t in tables}
        table_ids = [t.id for t in tables]
        id_to_name = {t.id: t.table_name.upper() for t in tables}

        cols_res = await self.db.execute(
            select(MetadataColumn).where(MetadataColumn.table_id.in_(table_ids))
        )
        col_by_key: dict[tuple[str, str], MetadataColumn] = {}
        columns_by_table: dict[str, set[str]] = {}
        for c in cols_res.scalars().all():
            tname = id_to_name.get(c.table_id)
            if not tname:
                continue
            cu = c.column_name.upper()
            col_by_key[(tname, cu)] = c
            columns_by_table.setdefault(tname, set()).add(cu)

        # Existing edges out of these tables, for idempotent re-runs.
        rel_res = await self.db.execute(
            select(MetadataRelation).where(MetadataRelation.from_table_id.in_(table_ids))
        )
        existing_edges = {
            (r.from_table_id, r.from_column_id, r.to_table_id, r.to_column_id)
            for r in rel_res.scalars().all()
        }

        tables_annotated = columns_annotated = relations_added = 0

        for name, table in tbl_by_name.items():
            p = prior.get(name)
            if not p:
                continue

            # Table description — fill only if empty.
            if not (table.ai_description or "").strip():
                desc = table_description(p)
                if desc:
                    table.ai_description = desc
                    tables_annotated += 1

            # Column descriptions — fill only if empty.
            present_cols = columns_by_table.get(name, set())
            for cu, text in column_descriptions(p).items():
                if cu not in present_cols:
                    continue
                col = col_by_key[(name, cu)]
                if not (col.ai_description or "").strip():
                    col.ai_description = text
                    columns_annotated += 1

            # Join edges — intersection-filtered, deduped.
            for e in join_edges(p, columns_by_table):
                from_tbl = tbl_by_name[e["from_table"]]
                to_tbl = tbl_by_name[e["to_table"]]
                from_col = col_by_key[(e["from_table"], e["from_column"])]
                to_col = col_by_key[(e["to_table"], e["to_column"])]
                key = (from_tbl.id, from_col.id, to_tbl.id, to_col.id)
                if key in existing_edges:
                    continue
                self.db.add(MetadataRelation(
                    tenant_id=self.tenant_id,
                    from_table_id=from_tbl.id,
                    from_column_id=from_col.id,
                    to_table_id=to_tbl.id,
                    to_column_id=to_col.id,
                    relation_type=_PRIOR_RELATION_TYPE,
                    confidence=e["confidence"],
                    is_admin_confirmed=False,
                    notes=e["purpose"],
                ))
                existing_edges.add(key)
                relations_added += 1

        await self.db.flush()
        log.info(
            "erpref_prior.applied",
            tables_annotated=tables_annotated,
            columns_annotated=columns_annotated,
            relations_added=relations_added,
        )
        return {
            "tables_annotated": tables_annotated,
            "columns_annotated": columns_annotated,
            "relations_added": relations_added,
        }
