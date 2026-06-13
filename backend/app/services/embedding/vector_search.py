"""
Vector Search — pgvector HNSW cosine similarity retrieval.

Spec: TR-001, TR-002, EM-007
- Tool retrieval: embed query → cosine search tool_embeddings → top-K tool IDs
- Entity retrieval: embed query → cosine search semantic_entity_embeddings → top-K entity IDs
- Document retrieval: embed query → cosine search document_embeddings → top-K chunk IDs
- Falls back to keyword ILIKE search when no embeddings exist for the tenant
- All vectors stored as JSON text; uses Python cosine similarity until pgvector migration runs

pgvector note: once the migration applies the real Vector type, replace the Python cosine
implementation with the native `<=>` operator for order-of-magnitude performance gain.
"""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.document import DocumentChunk, DocumentEmbedding
from app.models.semantic import SemanticEntity, SemanticEntityEmbedding
from app.models.tool import Tool, ToolEmbedding
from app.services.embedding.client import get_embedding_client

log = get_logger(__name__)

DEFAULT_TOP_K = 10
MIN_SIMILARITY = 0.60  # Discard candidates below this threshold


@dataclass
class ToolCandidate:
    tool_id: uuid.UUID
    tool_name: str
    description: str | None
    domain: str
    category: str
    similarity: float


@dataclass
class EntityCandidate:
    entity_id: uuid.UUID
    entity_name: str
    domain: str
    similarity: float


@dataclass
class ChunkCandidate:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    content: str
    similarity: float
    page_number: int | None
    section_title: str | None


class VectorSearchService:
    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id

    async def find_tools(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        domain: str | None = None,
    ) -> list[ToolCandidate]:
        """
        Find the most relevant tools for a natural-language query.
        Returns ranked list with similarity scores.
        """
        client = get_embedding_client()
        query_vec = await client.embed_single(query, input_type="query")

        # Load all active tool embeddings for the tenant
        q = (
            select(ToolEmbedding, Tool)
            .join(Tool, Tool.id == ToolEmbedding.tool_id)
            .where(
                ToolEmbedding.tenant_id == self.tenant_id,
                Tool.status == "active",
            )
        )
        if domain:
            q = q.where(Tool.domain == domain)

        result = await self.db.execute(q)
        rows = result.fetchall()

        if not rows:
            log.debug("vector_search.tools.no_embeddings", tenant_id=str(self.tenant_id))
            return await self._tool_keyword_fallback(query, top_k, domain)

        scored: list[tuple[float, ToolEmbedding, Tool]] = []
        for emb, tool in rows:
            try:
                stored_vec = _as_vector(emb.embedding)
                sim = _cosine_similarity(query_vec, stored_vec)
                if sim >= MIN_SIMILARITY:
                    scored.append((sim, emb, tool))
            except (json.JSONDecodeError, ValueError):
                pass

        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            ToolCandidate(
                tool_id=tool.id,
                tool_name=tool.name,
                description=tool.description,
                domain=tool.domain,
                category=tool.category,
                similarity=sim,
            )
            for sim, _, tool in scored[:top_k]
        ]

    async def find_entities(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
    ) -> list[EntityCandidate]:
        """Find the most relevant semantic entities for a query."""
        client = get_embedding_client()
        query_vec = await client.embed_single(query, input_type="query")

        result = await self.db.execute(
            select(SemanticEntityEmbedding, SemanticEntity)
            .join(SemanticEntity, SemanticEntity.id == SemanticEntityEmbedding.entity_id)
            .where(SemanticEntityEmbedding.tenant_id == self.tenant_id)
        )
        rows = result.fetchall()

        if not rows:
            return []

        scored: list[tuple[float, SemanticEntity]] = []
        for emb, entity in rows:
            try:
                stored_vec = _as_vector(emb.embedding)
                sim = _cosine_similarity(query_vec, stored_vec)
                if sim >= MIN_SIMILARITY:
                    scored.append((sim, entity))
            except (json.JSONDecodeError, ValueError):
                pass

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            EntityCandidate(
                entity_id=e.id,
                entity_name=e.entity_name,
                domain=e.domain,
                similarity=sim,
            )
            for sim, e in scored[:top_k]
        ]

    async def find_document_chunks(
        self,
        query: str,
        top_k: int = 5,
        min_similarity: float = MIN_SIMILARITY,
    ) -> list[ChunkCandidate]:
        """Find the most relevant document chunks for a RAG query."""
        client = get_embedding_client()
        query_vec = await client.embed_single(query, input_type="query")

        result = await self.db.execute(
            select(DocumentEmbedding, DocumentChunk)
            .join(DocumentChunk, DocumentChunk.id == DocumentEmbedding.chunk_id)
            .where(
                DocumentEmbedding.tenant_id == self.tenant_id,
                DocumentEmbedding.is_active.is_(True),
                DocumentChunk.is_active.is_(True),
            )
        )
        rows = result.fetchall()

        if not rows:
            return []

        scored: list[tuple[float, DocumentChunk]] = []
        for emb, chunk in rows:
            try:
                stored_vec = _as_vector(emb.embedding)
                sim = _cosine_similarity(query_vec, stored_vec)
                if sim >= min_similarity:
                    scored.append((sim, chunk))
            except (json.JSONDecodeError, ValueError):
                pass

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            ChunkCandidate(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                content=chunk.content,
                similarity=sim,
                page_number=chunk.page_number,
                section_title=chunk.section_title,
            )
            for sim, chunk in scored[:top_k]
        ]

    # ── Keyword fallback ──────────────────────────────────────────────────────

    async def _tool_keyword_fallback(
        self, query: str, top_k: int, domain: str | None
    ) -> list[ToolCandidate]:
        q = select(Tool).where(
            Tool.tenant_id == self.tenant_id,
            Tool.status == "active",
            Tool.name.ilike(f"%{query}%") | Tool.description.ilike(f"%{query}%"),
        )
        if domain:
            q = q.where(Tool.domain == domain)
        q = q.limit(top_k)
        result = await self.db.execute(q)
        tools = result.scalars().all()
        return [
            ToolCandidate(
                tool_id=t.id,
                tool_name=t.name,
                description=t.description,
                domain=t.domain,
                category=t.category,
                similarity=0.5,  # Nominal score for keyword hits
            )
            for t in tools
        ]


# ── Pure Python cosine similarity (replaced by pgvector <=> after migration) ──

def _as_vector(raw) -> list[float]:
    """Normalise a stored embedding to a list of floats.

    Columns are pgvector now (list / numpy array), but tolerate legacy
    JSON-text rows so a mixed table doesn't break retrieval.
    """
    if isinstance(raw, str):
        return json.loads(raw)
    return [float(x) for x in raw]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
