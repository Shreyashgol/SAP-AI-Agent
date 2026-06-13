"""
Knowledge Graph Traversal Service — BFS path-finding between entities.

Spec: KG-004, KG-007
- Max 5 hops per query
- Target latency < 500ms (NFR-P07)
- Only traverses edges that are admin_confirmed=True (confidence ≥ 0.8)
- Returns ordered join path with SQL ON conditions for query builder

Usage:
    traversal = GraphTraversal(db, tenant_id)
    path = await traversal.find_path(from_entity_id, to_entity_id)
    join_sql = traversal.build_join_sql(path)
"""

from __future__ import annotations

import uuid
from collections import deque
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.knowledge_graph import KnowledgeGraphEdge, KnowledgeGraphNode
from app.models.metadata import MetadataTable
from app.models.semantic import SemanticEntity

log = get_logger(__name__)

MAX_HOPS = 5


@dataclass
class PathStep:
    from_node_id: uuid.UUID
    to_node_id: uuid.UUID
    from_entity_name: str
    to_entity_name: str
    from_table: str
    to_table: str
    join_condition: str
    edge_type: str
    confidence: float


@dataclass
class TraversalPath:
    from_entity_id: uuid.UUID
    to_entity_id: uuid.UUID
    steps: list[PathStep] = field(default_factory=list)
    found: bool = False

    @property
    def hop_count(self) -> int:
        return len(self.steps)

    def entity_chain(self) -> list[str]:
        if not self.steps:
            return []
        chain = [self.steps[0].from_entity_name]
        for s in self.steps:
            chain.append(s.to_entity_name)
        return chain


class GraphTraversal:
    """BFS traversal of the knowledge graph to find join paths between entities."""

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self._node_cache: dict[uuid.UUID, KnowledgeGraphNode] = {}
        self._adj_cache: dict[uuid.UUID, list[KnowledgeGraphEdge]] | None = None

    async def find_path(
        self,
        from_entity_id: uuid.UUID,
        to_entity_id: uuid.UUID,
    ) -> TraversalPath:
        """
        BFS from from_entity to to_entity. Returns shortest path ≤ MAX_HOPS.
        Only uses confirmed edges.
        """
        if from_entity_id == to_entity_id:
            return TraversalPath(from_entity_id, to_entity_id, found=True)

        from_node = await self._node_for_entity(from_entity_id)
        to_node = await self._node_for_entity(to_entity_id)

        if not from_node or not to_node:
            log.debug("kg.traverse.node_missing",
                      from_entity=str(from_entity_id),
                      to_entity=str(to_entity_id))
            return TraversalPath(from_entity_id, to_entity_id, found=False)

        await self._load_adjacency()

        # BFS: queue of (current_node_id, path_of_edges)
        queue: deque[tuple[uuid.UUID, list[KnowledgeGraphEdge]]] = deque()
        queue.append((from_node.id, []))
        visited: set[uuid.UUID] = {from_node.id}

        while queue:
            current_id, path = queue.popleft()
            if len(path) >= MAX_HOPS:
                continue

            for edge in (self._adj_cache or {}).get(current_id, []):
                next_id = (
                    edge.to_node_id
                    if edge.from_node_id == current_id
                    else edge.from_node_id
                )
                if next_id in visited:
                    continue
                new_path = path + [edge]

                if next_id == to_node.id:
                    steps = await self._edges_to_steps(new_path)
                    return TraversalPath(
                        from_entity_id=from_entity_id,
                        to_entity_id=to_entity_id,
                        steps=steps,
                        found=True,
                    )

                visited.add(next_id)
                queue.append((next_id, new_path))

        return TraversalPath(from_entity_id, to_entity_id, found=False)

    async def find_paths_from(
        self, entity_id: uuid.UUID, max_hops: int = 2
    ) -> list[TraversalPath]:
        """
        Explore all reachable entities within max_hops.
        Used by the query planner to discover join candidates.
        """
        start_node = await self._node_for_entity(entity_id)
        if not start_node:
            return []

        await self._load_adjacency()

        results: list[TraversalPath] = []
        queue: deque[tuple[uuid.UUID, list[KnowledgeGraphEdge]]] = deque()
        queue.append((start_node.id, []))
        visited = {start_node.id}

        while queue:
            current_id, path = queue.popleft()
            if len(path) >= max_hops:
                continue

            for edge in (self._adj_cache or {}).get(current_id, []):
                next_id = (
                    edge.to_node_id
                    if edge.from_node_id == current_id
                    else edge.from_node_id
                )
                if next_id in visited:
                    continue

                new_path = path + [edge]
                visited.add(next_id)
                queue.append((next_id, new_path))

                next_node = await self._get_node(next_id)
                if next_node:
                    steps = await self._edges_to_steps(new_path)
                    results.append(TraversalPath(
                        from_entity_id=entity_id,
                        to_entity_id=next_node.entity_id,
                        steps=steps,
                        found=True,
                    ))

        return results

    def build_join_sql(self, path: TraversalPath) -> str:
        """
        Convert a traversal path into a SQL JOIN chain.
        Returns empty string if path has no steps (same table).
        """
        if not path.steps:
            return ""
        parts = []
        for step in path.steps:
            parts.append(
                f'JOIN "{step.to_table}" ON {step.join_condition}'
            )
        return "\n".join(parts)

    # ── Cache helpers ──────────────────────────────────────────────────────────

    async def _load_adjacency(self) -> None:
        if self._adj_cache is not None:
            return
        result = await self.db.execute(
            select(KnowledgeGraphEdge).where(
                KnowledgeGraphEdge.tenant_id == self.tenant_id,
                KnowledgeGraphEdge.is_admin_confirmed.is_(True),
                KnowledgeGraphEdge.join_condition.isnot(None),
            )
        )
        adj: dict[uuid.UUID, list[KnowledgeGraphEdge]] = {}
        for edge in result.scalars().all():
            adj.setdefault(edge.from_node_id, []).append(edge)
            adj.setdefault(edge.to_node_id, []).append(edge)  # bidirectional
        self._adj_cache = adj

    async def _get_node(self, node_id: uuid.UUID) -> KnowledgeGraphNode | None:
        if node_id in self._node_cache:
            return self._node_cache[node_id]
        result = await self.db.execute(
            select(KnowledgeGraphNode).where(KnowledgeGraphNode.id == node_id)
        )
        node = result.scalar_one_or_none()
        if node:
            self._node_cache[node_id] = node
        return node

    async def _node_for_entity(
        self, entity_id: uuid.UUID
    ) -> KnowledgeGraphNode | None:
        result = await self.db.execute(
            select(KnowledgeGraphNode).where(
                KnowledgeGraphNode.tenant_id == self.tenant_id,
                KnowledgeGraphNode.entity_id == entity_id,
            )
        )
        node = result.scalar_one_or_none()
        if node:
            self._node_cache[node.id] = node
        return node

    async def _edges_to_steps(
        self, edges: list[KnowledgeGraphEdge]
    ) -> list[PathStep]:
        steps: list[PathStep] = []
        for edge in edges:
            from_node = await self._get_node(edge.from_node_id)
            to_node = await self._get_node(edge.to_node_id)
            if not from_node or not to_node:
                continue

            from_table = await self._table_for_node(from_node)
            to_table = await self._table_for_node(to_node)

            steps.append(PathStep(
                from_node_id=edge.from_node_id,
                to_node_id=edge.to_node_id,
                from_entity_name=from_node.node_label,
                to_entity_name=to_node.node_label,
                from_table=from_table or "",
                to_table=to_table or "",
                join_condition=edge.join_condition or "",
                edge_type=edge.edge_type,
                confidence=edge.confidence,
            ))
        return steps

    async def _table_for_node(self, node: KnowledgeGraphNode) -> str | None:
        result = await self.db.execute(
            select(MetadataTable.table_name)
            .join(SemanticEntity, SemanticEntity.table_id == MetadataTable.id)
            .where(SemanticEntity.id == node.entity_id)
        )
        return result.scalar_one_or_none()
