"""
Conversation Manager — creates/retrieves conversations and persists turns.

Spec: CM-001, CM-002, CM-003, CM-004
  - CM-001: Conversation = ordered list of turns, scoped to tenant + user
  - CM-002: Each turn stores question, answer, agent lineage, timing, confidence
  - CM-003: Redis stores 24-hour sliding-window conversation context
  - CM-004: ConversationTurn written after graph completion (success or error)

Redis key format: conv:<conversation_id>:context
Redis TTL: 86400s (24h, refreshed on each new turn)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.conversation import Conversation, ConversationTurn

_log = get_logger("conversation.manager")
_CONTEXT_TTL = 86400  # 24 hours in seconds
_MAX_CONTEXT_TURNS = 10  # last N turns kept in Redis context window


class ConversationManager:
    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID) -> None:
        self._db = db
        self._tenant_id = tenant_id

    # ── CRUD ─────────────────────────────────────────────────────────────────

    async def create_conversation(
        self,
        user_id: uuid.UUID,
        title: str | None = None,
        connection_id: uuid.UUID | None = None,
    ) -> Conversation:
        conversation = Conversation(
            tenant_id=self._tenant_id,
            user_id=user_id,
            title=title,
            redis_session_key=None,
        )
        self._db.add(conversation)
        await self._db.commit()
        await self._db.refresh(conversation)
        _log.info("conversation.created", id=str(conversation.id))
        return conversation

    async def get_conversation(self, conversation_id: uuid.UUID) -> Conversation | None:
        result = await self._db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == self._tenant_id,
                Conversation.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def list_conversations(
        self, user_id: uuid.UUID, limit: int = 20, offset: int = 0
    ) -> list[Conversation]:
        result = await self._db.execute(
            select(Conversation)
            .where(
                Conversation.tenant_id == self._tenant_id,
                Conversation.user_id == user_id,
                Conversation.is_active.is_(True),
            )
            .order_by(Conversation.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_turn(self, turn_id: uuid.UUID) -> ConversationTurn | None:
        result = await self._db.execute(
            select(ConversationTurn).where(ConversationTurn.id == turn_id)
        )
        return result.scalar_one_or_none()

    async def truncate_turns(self, conversation_id: uuid.UUID, from_turn_number: int) -> None:
        """Delete all turns and their embeddings from the given turn number onwards."""
        # Get turn IDs that will be deleted
        turn_ids_query = select(ConversationTurn.id).where(
            ConversationTurn.conversation_id == conversation_id,
            ConversationTurn.turn_number >= from_turn_number
        )
        result = await self._db.execute(turn_ids_query)
        turn_ids = list(result.scalars().all())

        if turn_ids:
            # Delete embeddings
            from app.models.conversation import ConversationTurnEmbedding
            from sqlalchemy import delete
            await self._db.execute(
                delete(ConversationTurnEmbedding).where(
                    ConversationTurnEmbedding.turn_id.in_(turn_ids)
                )
            )

            # Delete turns
            await self._db.execute(
                delete(ConversationTurn).where(
                    ConversationTurn.conversation_id == conversation_id,
                    ConversationTurn.turn_number >= from_turn_number
                )
            )

        # Update conversation metadata
        conv = await self.get_conversation(conversation_id)
        if conv:
            conv.updated_at = datetime.now(timezone.utc)
            conv.turn_count = max(0, from_turn_number - 1)

        await self._db.commit()

        # Rebuild Redis context (short-term memory)
        try:
            from app.core.redis import get_redis
            redis = get_redis()
            key = f"conv:{conversation_id}:context"

            # Query remaining turns in order
            remaining_result = await self._db.execute(
                select(ConversationTurn)
                .where(ConversationTurn.conversation_id == conversation_id)
                .order_by(ConversationTurn.turn_number)
            )
            remaining_turns = remaining_result.scalars().all()

            context_list = []
            for t in remaining_turns:
                context_list.append({"role": "user", "content": t.question})
                if t.answer_text:
                    context_list.append({"role": "assistant", "content": t.answer_text})

            # Keep sliding window
            window = _MAX_CONTEXT_TURNS * 2
            if len(context_list) > window:
                context_list = context_list[-window:]

            if context_list:
                await redis.setex(key, _CONTEXT_TTL, json.dumps(context_list))
            else:
                await redis.delete(key)
        except Exception as exc:
            _log.warning("conversation.context_rebuild_fail", exc=str(exc))

    # ── Turn persistence ──────────────────────────────────────────────────────


    async def save_turn(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        question: str,
        answer_text: str | None,
        answer_data: dict | None,
        sql_query: str | None,
        chart_hint: str | None,
        follow_up_questions: list[str],
        lineage: dict | None,
        confidence_score: float | None,
        execution_time_ms: int | None,
        agents_invoked: list[str],
        intent: str | None = None,
        tool_id: uuid.UUID | None = None,
        error: str | None = None,
    ) -> ConversationTurn:
        # Get next turn number
        count_result = await self._db.execute(
            select(func.count(ConversationTurn.id)).where(
                ConversationTurn.conversation_id == conversation_id
            )
        )
        turn_number = (count_result.scalar() or 0) + 1

        error_log = {"message": error} if error else None

        turn = ConversationTurn(
            conversation_id=conversation_id,
            tenant_id=self._tenant_id,
            user_id=user_id,
            turn_number=turn_number,
            question=question,
            answer_text=answer_text,
            answer_data=answer_data,
            sql_query=sql_query,
            is_sql_generated=bool(sql_query),
            chart_hint=chart_hint,
            follow_up_questions=follow_up_questions,
            lineage=lineage,
            confidence_score=confidence_score,
            execution_time_ms=execution_time_ms,
            agents_invoked=agents_invoked,
            intent=intent,
            tool_id=tool_id,
            error_log=error_log,
        )
        self._db.add(turn)

        # Update conversation metadata
        conv = await self.get_conversation(conversation_id)
        if conv:
            conv.updated_at = datetime.now(timezone.utc)
            conv.turn_count = turn_number
            if not conv.title and question:
                conv.title = question[:120]

        await self._db.commit()
        await self._db.refresh(turn)

        # Update Redis context (short-term, within-conversation memory)
        await self._update_context(conversation_id, question, answer_text)

        # Long-term memory: embed this turn for cross-conversation recall.
        # Non-fatal — a failure here must never break turn persistence.
        from app.services.conversation.memory import ConversationMemoryService
        await ConversationMemoryService(self._db, self._tenant_id).embed_turn(
            turn_id=turn.id,
            conversation_id=conversation_id,
            user_id=user_id,
            question=question,
            answer=answer_text,
        )

        _log.info("conversation.turn_saved", turn_id=str(turn.id), turn_number=turn_number)
        return turn

    # ── Redis context window ──────────────────────────────────────────────────

    async def get_context(self, conversation_id: uuid.UUID) -> list[dict]:
        """Return the last N turns as a list of {role, content} dicts."""
        try:
            from app.core.redis import get_redis
            redis = get_redis()
            key = f"conv:{conversation_id}:context"
            raw = await redis.get(key)
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return []

    async def _update_context(
        self, conversation_id: uuid.UUID, question: str, answer: str | None
    ) -> None:
        try:
            from app.core.redis import get_redis
            redis = get_redis()
            key = f"conv:{conversation_id}:context"

            existing = await self.get_context(conversation_id)
            existing.append({"role": "user", "content": question})
            if answer:
                existing.append({"role": "assistant", "content": answer})

            # Keep sliding window
            window = _MAX_CONTEXT_TURNS * 2
            if len(existing) > window:
                existing = existing[-window:]

            await redis.setex(key, _CONTEXT_TTL, json.dumps(existing))
        except Exception as exc:
            _log.warning("conversation.context_update_fail", exc=str(exc))
