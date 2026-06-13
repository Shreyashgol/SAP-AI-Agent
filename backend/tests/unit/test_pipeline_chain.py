"""
Post-discovery pipeline tests.

Covers:
  - build_post_discovery_pipeline: Foundation (pack + early embeddings) →
    Phase B (independent engines, parallel) → Phase C (embedding join).
    Knowledge graph is excluded by default (MVP) and added via flag.
  - MSSQL fingerprinting (SL-011): SAP B1 schemas on MSSQL are detected
    and mapped to the sap_b1 entity pack.
"""

import uuid

import pytest
from celery import group
from celery.canvas import _chain

from app.services.semantic.mssql_fingerprint import fingerprint_connection
from app.worker.tasks.discovery import build_post_discovery_pipeline


def _branch_names(branch) -> tuple[str, ...]:
    """Task names of a Phase B branch (a bare signature or an inner chain)."""
    if isinstance(branch, _chain):
        return tuple(t.task for t in branch.tasks)
    return (branch.task,)


def _flatten(sig) -> list:
    out = []
    for stage in sig.tasks:
        if isinstance(stage, group):
            for branch in stage.tasks:
                out.extend(branch.tasks if isinstance(branch, _chain) else [branch])
        else:
            out.append(stage)
    return out


# ── Pipeline construction ─────────────────────────────────────────────────────

@pytest.mark.unit
def test_pipeline_phases() -> None:
    sig = build_post_discovery_pipeline("conn-1", "tenant-1", "mssql")
    foundation, early_embed, phase_b, phase_c = sig.tasks

    # Foundation: deterministic pack mapping, then an early embedding pass
    # so chat is usable before enrichment finishes
    assert foundation.task == "semantic.apply_pack"
    assert foundation.args == ("conn-1", "tenant-1", "mssql")
    assert early_embed.task == "embedding.embed_entities"

    # Phase B: independent engines in parallel; ordering only inside a branch
    assert isinstance(phase_b, group)
    branches = {_branch_names(b) for b in phase_b.tasks}
    assert branches == {
        ("semantic.run_ai_mapping",),                                  # AI Metadata
        ("semantic.seed_kpis", "tools.generate_kpi_tools"),            # KPI Engine
        ("tools.apply_tool_pack", "tools.generate_for_connection"),    # Tool Engine
    }

    # Phase C: final embedding join → pgvector
    assert isinstance(phase_c, group)
    assert {t.task for t in phase_c.tasks} == {
        "embedding.embed_entities",
        "embedding.embed_tools",
    }


@pytest.mark.unit
def test_knowledge_graph_excluded_from_mvp_but_available() -> None:
    mvp = build_post_discovery_pipeline("conn-1", "tenant-1", "mssql")
    assert "kg.build_full" not in [t.task for t in _flatten(mvp)]

    full = build_post_discovery_pipeline(
        "conn-1", "tenant-1", "mssql", include_knowledge_graph=True
    )
    kg = [t for t in _flatten(full) if t.task == "kg.build_full"]
    assert len(kg) == 1
    assert kg[0].args == ("conn-1", "tenant-1")
    assert kg[0].kwargs == {"triggered_by": "discovery"}


@pytest.mark.unit
def test_pipeline_signatures_are_immutable_with_correct_args() -> None:
    sig = build_post_discovery_pipeline("conn-1", "tenant-1", "mssql")
    all_sigs = _flatten(sig)
    assert all(t.immutable for t in all_sigs), "stages must ignore upstream results"

    by_name = {t.task: t for t in all_sigs}
    assert by_name["semantic.run_ai_mapping"].args == ("conn-1", "tenant-1")
    assert by_name["semantic.seed_kpis"].args == ("tenant-1",)
    assert by_name["tools.generate_for_connection"].args == ("conn-1", "tenant-1")
    assert by_name["embedding.embed_tools"].args == ("tenant-1",)


# ── MSSQL fingerprinting (SL-011) ─────────────────────────────────────────────

class _FakeResult:
    def __init__(self, names: list[str]) -> None:
        self._names = names

    def fetchall(self) -> list[tuple[str]]:
        return [(n,) for n in self._names]


class _FakeDB:
    def __init__(self, names: list[str]) -> None:
        self._names = names

    async def execute(self, _query) -> _FakeResult:
        return _FakeResult(self._names)


async def _fingerprint(table_names: list[str]):
    return await fingerprint_connection(
        _FakeDB(table_names), uuid.uuid4(), uuid.uuid4()  # type: ignore[arg-type]
    )


@pytest.mark.unit
async def test_sap_b1_on_mssql_is_detected() -> None:
    """A SAP B1 MSSQL schema (e.g. MEGATRADE_LIVE) must select the sap_b1 pack."""
    result = await _fingerprint(
        ["OCRD", "OINV", "ORDR", "OITM", "OJDT", "OPCH", "ORCT",
         "OSLP", "OWHS", "INV1", "RDR1", "OCPR", "OUSR", "CINF"]
    )
    assert result.detected_erp == "sap_b1"
    assert result.pack_source == "sap_b1"
    assert result.confidence >= 0.4


@pytest.mark.unit
async def test_dynamics_bc_still_detected() -> None:
    result = await _fingerprint(
        ["Company$General Ledger Entry", "Company$Customer Ledger Entry",
         "Company$Vendor Ledger Entry", "Company$Sales Header",
         "Company$Purchase Header", "Company$Item Ledger Entry",
         "Company$Item", "Company$Customer", "Company$Vendor",
         "Company$G/L Account"]
    )
    assert result.detected_erp == "dynamics_bc"
    assert result.pack_source == "mssql_dynamics"


@pytest.mark.unit
async def test_unknown_schema_falls_back_to_ai() -> None:
    result = await _fingerprint(["tbl_foo", "tbl_bar", "xyz123"])
    assert result.detected_erp == "unknown"
    assert result.pack_source == "ai_generated"


@pytest.mark.unit
async def test_empty_catalog_falls_back_to_ai() -> None:
    result = await _fingerprint([])
    assert result.detected_erp == "unknown"
    assert result.pack_source == "ai_generated"
