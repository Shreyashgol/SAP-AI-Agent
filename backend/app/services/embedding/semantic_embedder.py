"""
Semantic Entity Embedding Service — embeds SemanticEntity descriptions.

Spec: EM-006, TR-002
Used by the Intent Classifier and Tool Ranker to map NL questions to entities.
Stores embeddings in semantic_entity_embeddings table.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.semantic import SemanticEntity, SemanticEntityEmbedding
from app.services.embedding.client import get_embedding_client

log = get_logger(__name__)


def _entity_text(entity: SemanticEntity) -> str:
    """Build the embedding source text for a semantic entity."""
    return (
        f"{entity.entity_name} "
        f"{entity.description or ''} "
        f"domain:{entity.domain}"
    ).strip()


class SemanticEmbedder:
    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id

    async def embed_all(self, force: bool = False) -> dict[str, int]:
        """Embed all SemanticEntity records for the tenant."""
        entities_result = await self.db.execute(
            select(SemanticEntity).where(
                SemanticEntity.tenant_id == self.tenant_id,
            )
        )
        entities = entities_result.scalars().all()

        existing_result = await self.db.execute(
            select(SemanticEntityEmbedding.entity_id).where(
                SemanticEntityEmbedding.tenant_id == self.tenant_id
            )
        )
        existing_ids = {r[0] for r in existing_result.fetchall()}

        to_embed = [e for e in entities if force or e.id not in existing_ids]
        if not to_embed:
            return {"embedded": 0, "skipped": len(entities)}

        texts = [_entity_text(e) for e in to_embed]
        client = get_embedding_client()
        vectors = await client.embed_texts(texts, input_type="document")

        embedded = 0
        for entity, vector in zip(to_embed, vectors):
            await self._upsert(entity.id, vector)
            embedded += 1

        await self.db.flush()
        log.info("semantic_embedder.done",
                 tenant_id=str(self.tenant_id),
                 embedded=embedded, skipped=len(entities) - embedded)
        return {"embedded": embedded, "skipped": len(entities) - embedded}

    async def embed_entity(self, entity_id: uuid.UUID) -> None:
        """Embed a single entity."""
        result = await self.db.execute(
            select(SemanticEntity).where(
                SemanticEntity.id == entity_id,
                SemanticEntity.tenant_id == self.tenant_id,
            )
        )
        entity = result.scalar_one_or_none()
        if not entity:
            return
        client = get_embedding_client()
        vector = await client.embed_single(_entity_text(entity), input_type="document")
        await self._upsert(entity.id, vector)
        await self.db.flush()

    async def _upsert(self, entity_id: uuid.UUID, vector: list[float]) -> None:
        existing = await self.db.execute(
            select(SemanticEntityEmbedding).where(
                SemanticEntityEmbedding.entity_id == entity_id,
                SemanticEntityEmbedding.tenant_id == self.tenant_id,
            )
        )
        emb = existing.scalar_one_or_none()
        if emb:
            emb.embedding = vector
        else:
            self.db.add(SemanticEntityEmbedding(
                tenant_id=self.tenant_id,
                entity_id=entity_id,
                embedding=vector,
            ))
