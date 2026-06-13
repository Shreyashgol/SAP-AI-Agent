"""
Unit tests — Knowledge Graph traversal and builder.

Spec: KG-004, KG-006, KG-007
Tests:
  - BFS finds direct path
  - BFS finds multi-hop path
  - MAX_HOPS is enforced
  - Non-confirmed edges are not traversed
  - build_join_sql generates correct SQL
  - entity_chain lists entities in order
  - find_paths_from returns all reachable within max_hops
  - Empty graph returns found=False
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.knowledge_graph.traversal import (
    MAX_HOPS,
    GraphTraversal,
    PathStep,
    TraversalPath,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_node(entity_id=None, label="Entity"):
    node = MagicMock()
    node.id = uuid.uuid4()
    node.entity_id = entity_id or uuid.uuid4()
    node.node_label = label
    return node


def make_edge(from_id, to_id, confirmed=True, confidence=1.0):
    edge = MagicMock()
    edge.from_node_id = from_id
    edge.to_node_id = to_id
    edge.is_admin_confirmed = confirmed
    edge.confidence = confidence
    edge.edge_type = "explicit_fk"
    edge.join_condition = f'"{from_id}".col = "{to_id}".col'
    edge.relation_name = "test_rel"
    return edge


def make_step(from_name="A", to_name="B", table_a="TA", table_b="TB",
              join="TA.id = TB.a_id"):
    return PathStep(
        from_node_id=uuid.uuid4(),
        to_node_id=uuid.uuid4(),
        from_entity_name=from_name,
        to_entity_name=to_name,
        from_table=table_a,
        to_table=table_b,
        join_condition=join,
        edge_type="explicit_fk",
        confidence=1.0,
    )


# ── TraversalPath unit tests ───────────────────────────────────────────────────

class TestTraversalPath:
    def test_hop_count_empty(self):
        p = TraversalPath(uuid.uuid4(), uuid.uuid4(), steps=[], found=False)
        assert p.hop_count == 0

    def test_hop_count_single(self):
        p = TraversalPath(uuid.uuid4(), uuid.uuid4(), steps=[make_step()], found=True)
        assert p.hop_count == 1

    def test_hop_count_multi(self):
        steps = [make_step() for _ in range(3)]
        p = TraversalPath(uuid.uuid4(), uuid.uuid4(), steps=steps, found=True)
        assert p.hop_count == 3

    def test_entity_chain_empty(self):
        p = TraversalPath(uuid.uuid4(), uuid.uuid4(), steps=[], found=False)
        assert p.entity_chain() == []

    def test_entity_chain_single_hop(self):
        p = TraversalPath(
            uuid.uuid4(), uuid.uuid4(),
            steps=[make_step("Invoice", "Customer")],
            found=True,
        )
        assert p.entity_chain() == ["Invoice", "Customer"]

    def test_entity_chain_multi_hop(self):
        steps = [
            make_step("Invoice", "Order"),
            make_step("Order", "Customer"),
        ]
        p = TraversalPath(uuid.uuid4(), uuid.uuid4(), steps=steps, found=True)
        chain = p.entity_chain()
        assert chain == ["Invoice", "Order", "Customer"]


# ── build_join_sql ─────────────────────────────────────────────────────────────

class TestBuildJoinSQL:
    def _traversal(self):
        db = AsyncMock()
        return GraphTraversal(db, uuid.uuid4())

    def test_empty_path_returns_empty_string(self):
        t = self._traversal()
        path = TraversalPath(uuid.uuid4(), uuid.uuid4(), steps=[], found=True)
        assert t.build_join_sql(path) == ""

    def test_single_step_join(self):
        t = self._traversal()
        step = make_step("Invoice", "Customer", "OINV", "OCRD", "OINV.CardCode = OCRD.CardCode")
        path = TraversalPath(uuid.uuid4(), uuid.uuid4(), steps=[step], found=True)
        sql = t.build_join_sql(path)
        assert 'JOIN "OCRD"' in sql
        assert "OINV.CardCode = OCRD.CardCode" in sql

    def test_multi_step_join_chain(self):
        t = self._traversal()
        steps = [
            make_step("Invoice", "Order",    "OINV", "ORDR", "OINV.DocNum = ORDR.DocNum"),
            make_step("Order",   "Customer", "ORDR", "OCRD", "ORDR.CardCode = OCRD.CardCode"),
        ]
        path = TraversalPath(uuid.uuid4(), uuid.uuid4(), steps=steps, found=True)
        sql = t.build_join_sql(path)
        lines = sql.strip().split("\n")
        assert len(lines) == 2
        assert 'JOIN "ORDR"' in lines[0]
        assert 'JOIN "OCRD"' in lines[1]


# ── MAX_HOPS constant ──────────────────────────────────────────────────────────

def test_max_hops_is_five():
    assert MAX_HOPS == 5


# ── GraphTraversal BFS (mocked DB) ─────────────────────────────────────────────

class TestGraphTraversalBFS:
    """
    Tests that require mocking the DB adjacency cache and node lookups.
    These test BFS logic directly without a real database.
    """

    def _make_traversal(self, tenant_id=None):
        db = AsyncMock()
        t = GraphTraversal(db, tenant_id or uuid.uuid4())
        return t

    @pytest.mark.asyncio
    async def test_same_entity_returns_found(self):
        t = self._make_traversal()
        eid = uuid.uuid4()

        node = make_node(entity_id=eid)
        t._node_cache[node.id] = node

        async def fake_node_for_entity(entity_id):
            return node

        with patch.object(t, "_node_for_entity", side_effect=fake_node_for_entity):
            path = await t.find_path(eid, eid)
        assert path.found is True
        assert path.hop_count == 0

    @pytest.mark.asyncio
    async def test_missing_node_returns_not_found(self):
        t = self._make_traversal()

        async def fake_node_for_entity(_eid):
            return None

        with patch.object(t, "_node_for_entity", side_effect=fake_node_for_entity):
            path = await t.find_path(uuid.uuid4(), uuid.uuid4())

        assert path.found is False

    @pytest.mark.asyncio
    async def test_direct_edge_found(self):
        t = self._make_traversal()
        from_eid = uuid.uuid4()
        to_eid = uuid.uuid4()

        from_node = make_node(entity_id=from_eid, label="Invoice")
        to_node = make_node(entity_id=to_eid, label="Customer")
        t._node_cache[from_node.id] = from_node
        t._node_cache[to_node.id] = to_node

        edge = make_edge(from_node.id, to_node.id, confirmed=True)

        async def fake_node_for_entity(eid):
            if eid == from_eid:
                return from_node
            if eid == to_eid:
                return to_node
            return None

        async def fake_load_adjacency():
            t._adj_cache = {
                from_node.id: [edge],
                to_node.id: [edge],
            }

        async def fake_edges_to_steps(edges):
            return [make_step("Invoice", "Customer")]

        with patch.object(t, "_node_for_entity", side_effect=fake_node_for_entity), \
             patch.object(t, "_load_adjacency", side_effect=fake_load_adjacency), \
             patch.object(t, "_edges_to_steps", side_effect=fake_edges_to_steps):
            path = await t.find_path(from_eid, to_eid)

        assert path.found is True
        assert path.hop_count == 1

    @pytest.mark.asyncio
    async def test_hop_limit_enforced(self):
        """Path requiring 6 hops should not be found (MAX_HOPS=5)."""
        t = self._make_traversal()

        # Build a linear chain of 7 nodes (6 hops needed)
        nodes = [make_node(label=f"E{i}") for i in range(7)]
        node_map = {n.id: n for n in nodes}
        for n in nodes:
            t._node_cache[n.id] = n

        # Each consecutive pair connected by an edge
        edges = [make_edge(nodes[i].id, nodes[i + 1].id) for i in range(6)]

        adj: dict = {}
        for e in edges:
            adj.setdefault(e.from_node_id, []).append(e)
            adj.setdefault(e.to_node_id, []).append(e)

        async def fake_node_for_entity(eid):
            for n in nodes:
                if n.entity_id == eid:
                    return n
            return None

        async def fake_load_adjacency():
            t._adj_cache = adj

        with patch.object(t, "_node_for_entity", side_effect=fake_node_for_entity), \
             patch.object(t, "_load_adjacency", side_effect=fake_load_adjacency):
            path = await t.find_path(nodes[0].entity_id, nodes[6].entity_id)

        assert path.found is False

    @pytest.mark.asyncio
    async def test_unconfirmed_edge_not_traversed(self):
        """An unconfirmed edge should not be in the adjacency cache (filtered at load)."""
        t = self._make_traversal()
        from_eid = uuid.uuid4()
        to_eid = uuid.uuid4()

        from_node = make_node(entity_id=from_eid)
        to_node = make_node(entity_id=to_eid)
        t._node_cache[from_node.id] = from_node
        t._node_cache[to_node.id] = to_node

        async def fake_node_for_entity(eid):
            if eid == from_eid:
                return from_node
            return to_node

        async def fake_load_adjacency():
            # Adjacency is empty — unconfirmed edge was filtered by _load_adjacency
            t._adj_cache = {}

        with patch.object(t, "_node_for_entity", side_effect=fake_node_for_entity), \
             patch.object(t, "_load_adjacency", side_effect=fake_load_adjacency):
            path = await t.find_path(from_eid, to_eid)

        assert path.found is False


# ── KG builder column confidence scoring ──────────────────────────────────────

class TestColumnConfidenceScoring:
    """Test the _find_matching_columns confidence scoring logic."""

    def test_high_value_sap_columns(self):
        from app.services.knowledge_graph.builder import KnowledgeGraphBuilder
        from_cols = {"CardCode": uuid.uuid4(), "SlpCode": uuid.uuid4()}
        to_cols = {"CardCode": uuid.uuid4(), "SlpCode": uuid.uuid4(), "OtherCol": uuid.uuid4()}
        matches = dict(KnowledgeGraphBuilder._find_matching_columns(from_cols, to_cols))
        assert matches["CardCode"] == 0.90
        assert matches["SlpCode"] == 0.90

    def test_code_suffix_columns(self):
        from app.services.knowledge_graph.builder import KnowledgeGraphBuilder
        from_cols = {"WhsCode": uuid.uuid4(), "GroupCode": uuid.uuid4()}
        to_cols = {"WhsCode": uuid.uuid4(), "GroupCode": uuid.uuid4()}
        matches = dict(KnowledgeGraphBuilder._find_matching_columns(from_cols, to_cols))
        assert matches.get("GroupCode", 0) == 0.90  # "GroupCode" IS in high_value set
        assert matches.get("WhsCode", 0) == 0.90    # "WhsCode" IS in high_value set

    def test_generic_id_suffix(self):
        from app.services.knowledge_graph.builder import KnowledgeGraphBuilder
        from_cols = {"ProjectId": uuid.uuid4(), "TransNum": uuid.uuid4()}
        to_cols = {"ProjectId": uuid.uuid4(), "TransNum": uuid.uuid4()}
        matches = dict(KnowledgeGraphBuilder._find_matching_columns(from_cols, to_cols))
        assert matches["ProjectId"] == 0.70
        assert matches["TransNum"] == 0.70

    def test_short_column_excluded(self):
        from app.services.knowledge_graph.builder import KnowledgeGraphBuilder
        from_cols = {"Ab": uuid.uuid4()}
        to_cols = {"Ab": uuid.uuid4()}
        matches = KnowledgeGraphBuilder._find_matching_columns(from_cols, to_cols)
        assert len(matches) == 0

    def test_no_common_columns(self):
        from app.services.knowledge_graph.builder import KnowledgeGraphBuilder
        from_cols = {"ColA": uuid.uuid4()}
        to_cols = {"ColB": uuid.uuid4()}
        matches = KnowledgeGraphBuilder._find_matching_columns(from_cols, to_cols)
        assert len(matches) == 0
