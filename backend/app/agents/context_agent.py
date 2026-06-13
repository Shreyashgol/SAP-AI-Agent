"""
Conversation Context Agent — enriches the current question with prior turns.

Spec: AG-003-EXT, CTX-001, CTX-002, CTX-003
  - CTX-001: Reads last N turns from Redis session context
  - CTX-002: Asks Claude to resolve implicit references ("it", "them", "that period")
             and produce an enriched_question that is self-contained
  - CTX-003: Short-circuits on first question (no prior context) or very simple
             questions that have no pronoun/reference markers

Runs BEFORE intent_classifier so that all downstream agents work with a
fully-resolved, standalone question.

Performance:
  - Uses fast model (Haiku), target <150ms
  - Cache-friendly: skip enrichment when context is empty or question is long
    and doesn't contain any pronoun markers
"""

from __future__ import annotations

import re
from typing import Any

from app.agents.base import BaseAgent
from app.agents.state import AgentState

# Markers that suggest the question references prior context
_REFERENCE_MARKERS = re.compile(
    r"\b(it|its|they|them|their|that|those|this|these|"
    r"the same|previous|prior|last|above|aforementioned|"
    r"do the same|show me more|break it down|why|how about)\b",
    re.IGNORECASE,
)

_CONTEXT_SYSTEM = """\
You are a question enrichment assistant for an enterprise analytics platform.
Given the conversation history and a new question, rewrite the question so it
is completely self-contained and unambiguous — resolve all pronouns, implicit
references, and anaphora.

Rules:
- If the question is already self-contained, return it unchanged
- Only use information from the provided conversation history
- Do NOT invent new filter values or time periods not mentioned in context
- Keep the rewrite concise — do not add explanation
- Output ONLY the rewritten question as plain text (no JSON, no quotes, no markdown)
"""


class ContextAgent(BaseAgent):
    name = "context_agent"

    async def _run(self, state: AgentState) -> dict[str, Any]:
        question = state["question"]
        conversation_id = state.get("conversation_id")

        # Skip if no conversation context available
        if not conversation_id:
            return {"enriched_question": question}

        # Load Redis context window
        context_turns: list[dict] = []
        try:
            from app.services.conversation.manager import ConversationManager
            from app.db.session import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                mgr = ConversationManager(db, state["tenant_id"])
                context_turns = await mgr.get_context(conversation_id)
        except Exception as exc:
            self._log.warning("context_agent.context_load_fail", exc=str(exc))

        # No prior turns — first question, nothing to enrich
        if not context_turns:
            return {"enriched_question": question}

        # Heuristic: skip enrichment if question has no reference markers
        # (saves a Claude call for the common case)
        if not _REFERENCE_MARKERS.search(question):
            return {"enriched_question": question}

        # Build compact history string (last 6 messages max)
        recent = context_turns[-6:]
        history_lines = []
        for turn in recent:
            role = turn.get("role", "user")
            content = str(turn.get("content", ""))[:300]  # truncate long answers
            history_lines.append(f"{role.upper()}: {content}")
        history = "\n".join(history_lines)

        user_msg = f"Conversation history:\n{history}\n\nNew question: {question}"

        enriched = await self._call_llm(
            system=_CONTEXT_SYSTEM,
            user=user_msg,
            max_tokens=256,
        )

        enriched = enriched.strip().strip('"').strip("'")

        # Sanity check — if Claude returned something nonsensical, use original
        if not enriched or len(enriched) < 3:
            enriched = question

        self._log.info(
            "context_agent.enriched",
            original=question[:80],
            enriched=enriched[:80],
            changed=(enriched.lower() != question.lower()),
        )

        return {"enriched_question": enriched}
