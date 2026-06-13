"""
Tool Ranking Engine — scores tool candidates for a given NL query.

Spec: TR-001, TR-002, TR-003, TR-004
Score formula (0–1):
  final_score = (
      0.60 * semantic_similarity   # vector cosine from VectorSearchService
    + 0.25 * success_rate          # from ToolRankingWeight.success_rate
    + 0.10 * feedback_weight       # from ToolRankingWeight.feedback_weight  (FL-005)
    + 0.05 * domain_match_bonus    # 1.0 if tool domain matches detected domain, else 0
  )

Weights are intentionally hard-coded at Phase-1; Phase-3 will tune them via A/B testing.

TR-004: nightly weight recalculation task (tools.recalculate_weights) updates
        success_rate and feedback_weight from UserFeedback + ConversationTurn history.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.tool import Tool, ToolRankingWeight
from app.services.embedding.vector_search import ToolCandidate, VectorSearchService

log = get_logger(__name__)

# Scoring weights (must sum to 1.0)
W_SEMANTIC   = 0.60
W_SUCCESS    = 0.25
W_FEEDBACK   = 0.10
W_DOMAIN     = 0.05

TOP_K_CANDIDATES = 20  # retrieve this many from vector search before rescoring
TOP_K_RETURN = 5       # return best N after rescoring


@dataclass
class RankedTool:
    tool_id: uuid.UUID
    tool_name: str
    description: str | None
    domain: str
    category: str
    final_score: float
    semantic_similarity: float
    success_rate: float
    feedback_weight: float


class ToolRanker:
    def __init__(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id

    async def rank(
        self,
        query: str,
        detected_domain: str | None = None,
        top_k: int = TOP_K_RETURN,
    ) -> list[RankedTool]:
        """
        Retrieve top-K tool candidates via vector search then rescore with
        success-rate and feedback weights.
        """
        search = VectorSearchService(self.db, self.tenant_id)
        candidates = await search.find_tools(
            query,
            top_k=TOP_K_CANDIDATES,
            domain=detected_domain,
        )

        if not candidates:
            return []

        # Batch-load ranking weights
        tool_ids = [c.tool_id for c in candidates]
        weights_result = await self.db.execute(
            select(ToolRankingWeight).where(
                ToolRankingWeight.tenant_id == self.tenant_id,
                ToolRankingWeight.tool_id.in_(tool_ids),
            )
        )
        weight_map: dict[uuid.UUID, ToolRankingWeight] = {
            w.tool_id: w for w in weights_result.scalars().all()
        }

        ranked: list[RankedTool] = []
        for cand in candidates:
            w = weight_map.get(cand.tool_id)
            success_rate   = w.success_rate    if w else 0.0
            feedback_wt    = w.feedback_weight if w else 0.0
            domain_bonus   = 1.0 if (detected_domain and cand.domain == detected_domain) else 0.0

            final = (
                W_SEMANTIC * cand.similarity
                + W_SUCCESS  * success_rate
                + W_FEEDBACK * feedback_wt
                + W_DOMAIN   * domain_bonus
            )
            ranked.append(RankedTool(
                tool_id=cand.tool_id,
                tool_name=cand.tool_name,
                description=cand.description,
                domain=cand.domain,
                category=cand.category,
                final_score=round(final, 4),
                semantic_similarity=round(cand.similarity, 4),
                success_rate=round(success_rate, 4),
                feedback_weight=round(feedback_wt, 4),
            ))

        ranked.sort(key=lambda r: r.final_score, reverse=True)
        log.debug("tool_ranker.ranked",
                  query=query[:60], top=ranked[0].tool_name if ranked else None,
                  candidate_count=len(ranked))
        return ranked[:top_k]

    async def update_weights(self) -> dict[str, int]:
        """
        Recalculate success_rate and feedback_weight for all tools in this tenant.
        Called nightly by tools.recalculate_weights Celery task (TR-004).

        success_rate  = (turns where tool used AND no negative feedback) / total turns with tool
        feedback_weight = (positive_feedback_count - negative_feedback_count) / total_feedback
                          clamped to [0, 1]
        """
        from app.models.conversation import ConversationTurn
        from app.models.feedback import UserFeedback

        # Get all tools for this tenant
        tools_result = await self.db.execute(
            select(Tool.id).where(
                Tool.tenant_id == self.tenant_id,
                Tool.status == "active",
            )
        )
        tool_ids = [r[0] for r in tools_result.fetchall()]
        updated = 0

        for tool_id in tool_ids:
            # Count total turns using this tool
            turns_result = await self.db.execute(
                select(ConversationTurn).where(
                    ConversationTurn.tenant_id == self.tenant_id,
                    ConversationTurn.tool_id == tool_id,
                )
            )
            turns = turns_result.scalars().all()
            total_turns = len(turns)

            # Count feedback
            turn_ids = [t.id for t in turns]
            if turn_ids:
                feedback_result = await self.db.execute(
                    select(UserFeedback).where(
                        UserFeedback.tenant_id == self.tenant_id,
                        UserFeedback.conversation_turn_id.in_(turn_ids),
                    )
                )
                feedback_rows = feedback_result.scalars().all()
                positive = sum(1 for f in feedback_rows if f.rating > 0)
                negative = sum(1 for f in feedback_rows if f.rating < 0)
                total_feedback = len(feedback_rows)
            else:
                positive = negative = total_feedback = 0

            success_rate = (
                (positive / total_turns) if total_turns > 0 else 0.0
            )
            feedback_wt = (
                max(0.0, min(1.0, (positive - negative) / total_feedback))
                if total_feedback > 0
                else 0.0
            )

            # Upsert
            existing = await self.db.execute(
                select(ToolRankingWeight).where(
                    ToolRankingWeight.tenant_id == self.tenant_id,
                    ToolRankingWeight.tool_id == tool_id,
                )
            )
            weight = existing.scalar_one_or_none()
            if weight:
                weight.success_rate = success_rate
                weight.feedback_weight = feedback_wt
                weight.execution_count = total_turns
            else:
                from datetime import UTC, datetime
                self.db.add(ToolRankingWeight(
                    tenant_id=self.tenant_id,
                    tool_id=tool_id,
                    success_rate=success_rate,
                    feedback_weight=feedback_wt,
                    execution_count=total_turns,
                    last_recalculated_at=datetime.now(UTC).isoformat(),
                ))
            updated += 1

        await self.db.flush()
        log.info("tool_ranker.weights_updated",
                 tenant_id=str(self.tenant_id), count=updated)
        return {"updated": updated}
