"""
Conversation Memory Service — long-term, cross-conversation recall.

Embeds each conversation turn (question + answer) and semantically retrieves the
most relevant prior turns across ALL of a user's conversations, so the assistant
can recall things discussed in earlier sessions ("what did we conclude about
Delhi sales last week?").

Storage: conversation_turn_embeddings (pgvector vector(1024), HNSW cosine index).
Embeddings: local bge-large via the shared embedding client (no API cost).
Scope: always filtered to tenant_id + user_id — recall never crosses users.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.conversation import ConversationTurnEmbedding
from app.services.embedding.client import get_embedding_client

log = get_logger("conversation.memory")

# Only surface recalled turns this similar or better (cosine, 0..1).
DEFAULT_MIN_SIMILARITY = 0.55
DEFAULT_TOP_K = 3
_MAX_ANSWER_CHARS = 600


@dataclass
class RecalledTurn:
    turn_id: uuid.UUID
    conversation_id: uuid.UUID
    content: str
    similarity: float


class ConversationMemoryService:
    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID) -> None:
        self._db = db
        self._tenant_id = tenant_id

    @staticmethod
    def _build_content(question: str, answer: str | None) -> str:
        ans = (answer or "").strip()[:_MAX_ANSWER_CHARS]
        return f"Q: {question}\nA: {ans}" if ans else f"Q: {question}"

    async def embed_turn(
        self,
        turn_id: uuid.UUID,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        question: str,
        answer: str | None,
    ) -> None:
        """Embed and persist one turn for future recall. Idempotent per turn_id.
        Non-fatal: never raises into the caller's turn-save path."""
        try:
            content = self._build_content(question, answer)
            vector = await get_embedding_client().embed_single(content, input_type="document")

            existing = await self._db.execute(
                select(ConversationTurnEmbedding).where(
                    ConversationTurnEmbedding.turn_id == turn_id
                )
            )
            row = existing.scalar_one_or_none()
            if row:
                row.content = content
                row.embedding = vector
            else:
                self._db.add(ConversationTurnEmbedding(
                    tenant_id=self._tenant_id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    turn_id=turn_id,
                    content=content,
                    embedding=vector,
                ))
            await self._db.commit()
            log.info("conversation.memory.embedded", turn_id=str(turn_id))
        except Exception as exc:
            await self._db.rollback()
            log.warning("conversation.memory.embed_fail", turn_id=str(turn_id), exc=str(exc))

    async def recall(
        self,
        query: str,
        user_id: uuid.UUID,
        top_k: int = DEFAULT_TOP_K,
        exclude_conversation_id: uuid.UUID | None = None,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
    ) -> list[RecalledTurn]:
        """Return the most semantically relevant prior turns for this user,
        across conversations. The current conversation is excluded so recall is
        strictly long-term (short-term context is handled by the Redis window)."""
        try:
            qvec = await get_embedding_client().embed_single(query, input_type="query")
            distance = ConversationTurnEmbedding.embedding.cosine_distance(qvec)
            stmt = (
                select(ConversationTurnEmbedding, distance.label("distance"))
                .where(
                    ConversationTurnEmbedding.tenant_id == self._tenant_id,
                    ConversationTurnEmbedding.user_id == user_id,
                )
                .order_by(distance)
                .limit(top_k)
            )
            if exclude_conversation_id is not None:
                stmt = stmt.where(
                    ConversationTurnEmbedding.conversation_id != exclude_conversation_id
                )
            result = await self._db.execute(stmt)

            recalled: list[RecalledTurn] = []
            for row, dist in result.all():
                similarity = 1.0 - float(dist)
                if similarity >= min_similarity:
                    recalled.append(RecalledTurn(
                        turn_id=row.turn_id,
                        conversation_id=row.conversation_id,
                        content=row.content,
                        similarity=round(similarity, 4),
                    ))
            log.info("conversation.memory.recalled", query=query[:60], hits=len(recalled))
            return recalled
        except Exception as exc:
            log.warning("conversation.memory.recall_fail", exc=str(exc))
            return []
