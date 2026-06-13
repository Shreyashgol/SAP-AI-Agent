"""
Knowledge Graph Builder — constructs KG nodes and edges from the semantic layer.

Sources:
  - Nodes:  one per SemanticEntity (KG-001)
  - Edges:  explicit FK from MetadataRelation (confidence 1.0) (KG-002)
           inferred from column-name pattern matching (confidence 0.5–0.9) (KG-003)
  - Edges with confidence < 0.8 require admin confirmation before SQL use (KG-006)

Refresh strategy:
  - Full rebuild replaces all existing nodes/edges for the connection
  - Incremental adds new nodes/edges, keeps confirmed edges
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.knowledge_graph import KnowledgeGraphEdge, KnowledgeGraphNode
from app.models.metadata import MetadataColumn, MetadataRelation, MetadataTable
from app.models.semantic import SemanticAttribute, SemanticEntity

log = get_logger(__name__)

INFERRED_CONFIDENCE_THRESHOLD = 0.8  # Below this → requires admin confirm
MIN_INFER_CONFIDENCE = 0.45          # Don't store edges below this


@dataclass
class EdgeCandidate:
    from_entity_id: uuid.UUID
    to_entity_id: uuid.UUID
    from_col: str
    to_col: str
    relation_name: str
    edge_type: str   # explicit_fk | inferred_name
    confidence: float
    join_condition: str


class KnowledgeGraphBuilder:
    """Builds / refreshes the KG for a specific connection."""

    def __init__(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.connection_id = connection_id

    # ── Public API ────────────────────────────────────────────────────────────

    async def build_full(self) -> dict[str, int]:
        """
        Full rebuild: drop all non-confirmed edges for this connection's entities,
        re-create all nodes and edges from current metadata + semantic layer.
        """
        entity_ids = await self._get_connection_entity_ids()
        if not entity_ids:
            log.info("kg.build.no_entities", connection_id=str(self.connection_id))
            return {"nodes": 0, "edges_explicit": 0, "edges_inferred": 0}

        # Remove non-confirmed edges (keep admin-confirmed ones)
        await self._delete_unconfirmed_edges(entity_ids)

        nodes = await self._upsert_nodes(entity_ids)
        node_map = {n.entity_id: n.id for n in nodes}

        explicit = await self._build_explicit_edges(entity_ids, node_map)
        inferred = await self._build_inferred_edges(entity_ids, node_map)

        await self.db.flush()
        log.info("kg.build.full.done",
                 nodes=len(nodes), explicit=explicit, inferred=inferred,
                 connection_id=str(self.connection_id))
        return {"nodes": len(nodes), "edges_explicit": explicit, "edges_inferred": inferred}

    async def refresh_for_entity(self, entity_id: uuid.UUID) -> None:
        """Refresh KG for a single entity after catalog change (KG-009)."""
        entity_ids = {entity_id}
        nodes = await self._upsert_nodes(entity_ids)
        node_map = {n.entity_id: n.id for n in nodes}
        await self._build_explicit_edges(entity_ids, node_map)
        await self.db.flush()

    # ── Node upsert ───────────────────────────────────────────────────────────

    async def _upsert_nodes(
        self, entity_ids: set[uuid.UUID]
    ) -> list[KnowledgeGraphNode]:
        nodes: list[KnowledgeGraphNode] = []
        for eid in entity_ids:
            entity_result = await self.db.execute(
                select(SemanticEntity).where(SemanticEntity.id == eid)
            )
            entity = entity_result.scalar_one_or_none()
            if not entity:
                continue

            existing = await self.db.execute(
                select(KnowledgeGraphNode).where(
                    KnowledgeGraphNode.tenant_id == self.tenant_id,
                    KnowledgeGraphNode.entity_id == eid,
                )
            )
            node = existing.scalar_one_or_none()
            if node is None:
                node = KnowledgeGraphNode(
                    tenant_id=self.tenant_id,
                    entity_id=eid,
                    node_label=entity.entity_name,
                    domain=entity.domain,
                    node_properties={
                        "pack_source": entity.pack_source,
                        "confidence": entity.confidence,
                    },
                )
                self.db.add(node)
                await self.db.flush()
            else:
                node.node_label = entity.entity_name
                node.domain = entity.domain

            nodes.append(node)
        return nodes

    # ── Explicit FK edges ─────────────────────────────────────────────────────

    async def _build_explicit_edges(
        self,
        entity_ids: set[uuid.UUID],
        node_map: dict[uuid.UUID, uuid.UUID],  # entity_id → node_id
    ) -> int:
        """Build edges from MetadataRelation (explicit_fk type, confidence=1.0)."""
        # Load all FK relations for tables owned by this connection
        tables_result = await self.db.execute(
            select(MetadataTable.id).where(
                MetadataTable.connection_id == self.connection_id,
                MetadataTable.tenant_id == self.tenant_id,
            )
        )
        table_ids = {r[0] for r in tables_result.fetchall()}

        relations_result = await self.db.execute(
            select(MetadataRelation).where(
                MetadataRelation.tenant_id == self.tenant_id,
                MetadataRelation.from_table_id.in_(table_ids),
            )
        )
        relations = relations_result.scalars().all()

        count = 0
        for rel in relations:
            from_node = await self._node_for_table(rel.from_table_id, node_map)
            to_node = await self._node_for_table(rel.to_table_id, node_map)
            if not from_node or not to_node or from_node == to_node:
                continue

            # Get column names for join condition
            from_col = await self._col_name(rel.from_column_id)
            to_col = await self._col_name(rel.to_column_id)
            if not from_col or not to_col:
                continue

            from_table = await self._table_name(rel.from_table_id)
            to_table = await self._table_name(rel.to_table_id)
            join_cond = (
                f'"{from_table}"."{from_col}" = "{to_table}"."{to_col}"'
            )
            relation_name = f"{from_col}_to_{to_col}"

            if await self._edge_exists(from_node, to_node, relation_name):
                continue

            self.db.add(KnowledgeGraphEdge(
                tenant_id=self.tenant_id,
                from_node_id=from_node,
                to_node_id=to_node,
                relation_name=relation_name,
                edge_type="explicit_fk",
                weight=1.0,
                confidence=1.0,
                is_admin_confirmed=True,
                join_condition=join_cond,
            ))
            count += 1

        return count

    # ── Inferred edges ────────────────────────────────────────────────────────

    async def _build_inferred_edges(
        self,
        entity_ids: set[uuid.UUID],
        node_map: dict[uuid.UUID, uuid.UUID],
    ) -> int:
        """
        Infer edges by matching column name patterns across entities.
        e.g. OINV.CardCode → OCRD.CardCode with confidence 0.85.
        """
        # Build column index: {entity_id → {col_name: col_id}}
        col_index: dict[uuid.UUID, dict[str, uuid.UUID]] = {}
        for eid in entity_ids:
            entity = await self.db.execute(
                select(SemanticEntity).where(SemanticEntity.id == eid)
            )
            ent = entity.scalar_one_or_none()
            if not ent:
                continue
            cols_result = await self.db.execute(
                select(MetadataColumn.column_name, MetadataColumn.id)
                .join(MetadataTable, MetadataTable.id == MetadataColumn.table_id)
                .where(
                    MetadataTable.id == ent.table_id,
                    MetadataColumn.is_foreign_key.is_(False),
                )
            )
            col_index[eid] = {r[0]: r[1] for r in cols_result.fetchall()}

        count = 0
        entity_list = list(entity_ids)

        for i, from_eid in enumerate(entity_list):
            from_cols = col_index.get(from_eid, {})
            from_node = node_map.get(from_eid)
            if not from_node:
                continue

            for to_eid in entity_list[i + 1:]:
                to_cols = col_index.get(to_eid, {})
                to_node = node_map.get(to_eid)
                if not to_node:
                    continue

                matches = self._find_matching_columns(from_cols, to_cols)
                for col_name, confidence in matches:
                    if confidence < MIN_INFER_CONFIDENCE:
                        continue
                    if await self._edge_exists(from_node, to_node, f"infer_{col_name}"):
                        continue

                    from_table = await self._table_for_entity(from_eid)
                    to_table = await self._table_for_entity(to_eid)
                    join_cond = (
                        f'"{from_table}"."{col_name}" = "{to_table}"."{col_name}"'
                        if from_table and to_table else None
                    )

                    self.db.add(KnowledgeGraphEdge(
                        tenant_id=self.tenant_id,
                        from_node_id=from_node,
                        to_node_id=to_node,
                        relation_name=f"infer_{col_name}",
                        edge_type="inferred_name",
                        weight=confidence,
                        confidence=confidence,
                        is_admin_confirmed=confidence >= INFERRED_CONFIDENCE_THRESHOLD,
                        join_condition=join_cond,
                    ))
                    count += 1

        return count

    @staticmethod
    def _find_matching_columns(
        from_cols: dict[str, uuid.UUID],
        to_cols: dict[str, uuid.UUID],
    ) -> list[tuple[str, float]]:
        """
        Return (col_name, confidence) pairs where column names match across tables.
        Higher confidence for primary-key-style names (CardCode, DocEntry, etc.).
        """
        matches: list[tuple[str, float]] = []
        # High-value SAP B1 join columns
        high_value = {
            "CardCode", "ItemCode", "SlpCode", "WhsCode", "PriceList",
            "ItmsGrpCod", "CurrCode", "Territory", "GroupCode",
        }
        for col in set(from_cols) & set(to_cols):
            col_upper = col
            if col_upper in high_value:
                confidence = 0.90
            elif re.search(r'(Code|Num|Id|Key)$', col, re.IGNORECASE):
                confidence = 0.70
            elif len(col) >= 4:
                confidence = 0.50
            else:
                continue
            matches.append((col, confidence))
        return matches

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _get_connection_entity_ids(self) -> set[uuid.UUID]:
        tables_result = await self.db.execute(
            select(MetadataTable.id).where(
                MetadataTable.connection_id == self.connection_id,
                MetadataTable.tenant_id == self.tenant_id,
            )
        )
        table_ids = [r[0] for r in tables_result.fetchall()]
        if not table_ids:
            return set()

        entities_result = await self.db.execute(
            select(SemanticEntity.id).where(
                SemanticEntity.tenant_id == self.tenant_id,
                SemanticEntity.table_id.in_(table_ids),
            )
        )
        return {r[0] for r in entities_result.fetchall()}

    async def _delete_unconfirmed_edges(self, entity_ids: set[uuid.UUID]) -> None:
        node_ids_result = await self.db.execute(
            select(KnowledgeGraphNode.id).where(
                KnowledgeGraphNode.tenant_id == self.tenant_id,
                KnowledgeGraphNode.entity_id.in_(entity_ids),
            )
        )
        node_ids = [r[0] for r in node_ids_result.fetchall()]
        if not node_ids:
            return
        await self.db.execute(
            delete(KnowledgeGraphEdge).where(
                KnowledgeGraphEdge.tenant_id == self.tenant_id,
                KnowledgeGraphEdge.from_node_id.in_(node_ids),
                KnowledgeGraphEdge.is_admin_confirmed.is_(False),
            )
        )

    async def _node_for_table(
        self, table_id: uuid.UUID, node_map: dict[uuid.UUID, uuid.UUID]
    ) -> uuid.UUID | None:
        entity_result = await self.db.execute(
            select(SemanticEntity.id).where(
                SemanticEntity.table_id == table_id,
                SemanticEntity.tenant_id == self.tenant_id,
            )
        )
        row = entity_result.scalar_one_or_none()
        if not row:
            return None
        return node_map.get(row)

    async def _edge_exists(
        self, from_node: uuid.UUID, to_node: uuid.UUID, relation_name: str
    ) -> bool:
        result = await self.db.execute(
            select(KnowledgeGraphEdge.id).where(
                KnowledgeGraphEdge.from_node_id == from_node,
                KnowledgeGraphEdge.to_node_id == to_node,
                KnowledgeGraphEdge.relation_name == relation_name,
            )
        )
        return result.scalar_one_or_none() is not None

    async def _col_name(self, col_id: uuid.UUID) -> str | None:
        result = await self.db.execute(
            select(MetadataColumn.column_name).where(MetadataColumn.id == col_id)
        )
        return result.scalar_one_or_none()

    async def _table_name(self, table_id: uuid.UUID) -> str | None:
        result = await self.db.execute(
            select(MetadataTable.table_name).where(MetadataTable.id == table_id)
        )
        return result.scalar_one_or_none()

    async def _table_for_entity(self, entity_id: uuid.UUID) -> str | None:
        result = await self.db.execute(
            select(MetadataTable.table_name)
            .join(SemanticEntity, SemanticEntity.table_id == MetadataTable.id)
            .where(SemanticEntity.id == entity_id)
        )
        return result.scalar_one_or_none()
