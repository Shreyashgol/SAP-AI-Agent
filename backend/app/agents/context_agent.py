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
    r"\b(it|its|they|them|their|that|those|this|these|one|ones|"
    r"the same|previous|prior|last|above|aforementioned|former|latter|"
    r"do the same|show me more|break it down|why|how about|what about|"
    r"just the|the top|the bottom|the highest|the lowest|instead|"
    r"drill|same period|same thing)\b",
    re.IGNORECASE,
)

# Meta-questions ABOUT the conversation itself (answered from history, not data).
_META_PREV_QUESTION = re.compile(
    r"\b(what\s+(was|were)\s+(my|the)\s+(previous|last|prior|earlier)\s+(question|quer)"
    r"|what\s+did\s+i\s+(just\s+)?ask"
    r"|repeat\s+my\s+(previous|last)\s+question)\b",
    re.IGNORECASE,
)
_META_PREV_ANSWER = re.compile(
    r"\b(what\s+did\s+you\s+(just\s+)?say"
    r"|your\s+(previous|last)\s+(answer|response)"
    r"|repeat\s+(your|the)\s+(previous|last)\s+answer)\b",
    re.IGNORECASE,
)
_META_SUMMARY = re.compile(
    r"\b(summari[sz]e|recap|what have we)\b.*\b(conversation|chat|discuss|talk|so far)\b",
    re.IGNORECASE,
)

# Questions that explicitly ask to recall something from earlier conversations
# (answered from long-term memory, not by re-querying the database).
_RECALL_INTENT = re.compile(
    r"\b(did we|have we|what did we|remind me|last time|in the past|"
    r"earlier (you|we|conversation)|previously (discuss|said|told|looked|covered)|"
    r"you (told|said) me|we (discussed|talked|looked|concluded|covered|analy[sz]ed))\b",
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
        user_id = state.get("user_id")

        # Skip if no conversation context available
        if not conversation_id:
            return {"enriched_question": question}

        # Load short-term window (current conversation, from Redis) AND long-term
        # recall (semantically relevant turns from the user's OTHER conversations).
        context_turns: list[dict] = []
        recalled: list = []
        try:
            from app.services.conversation.manager import ConversationManager
            from app.services.conversation.memory import ConversationMemoryService
            from app.db.session import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                context_turns = await ConversationManager(
                    db, state["tenant_id"]
                ).get_context(conversation_id)
                if user_id:
                    recalled = await ConversationMemoryService(db, state["tenant_id"]).recall(
                        question,
                        user_id=user_id,
                        exclude_conversation_id=conversation_id,
                    )
        except Exception as exc:
            self._log.warning("context_agent.context_load_fail", exc=str(exc))

        # Meta-questions ABOUT the current conversation are answered from its
        # history here, short-circuiting the data pipeline (supervisor routes to
        # END when answer_text is set). Otherwise "what was my previous question?"
        # gets mis-rewritten into the prior question and sent to the SQL planner.
        if context_turns:
            meta = self._answer_meta(question, context_turns)
            if meta is not None:
                self._log.info("context_agent.meta_answered", question=question[:80])
                return self._terminal(question, meta, "Meta")

        # Long-term recall: when the user explicitly asks about an earlier
        # discussion and we found relevant prior turns, answer from memory
        # directly rather than re-querying the database.
        if recalled and _RECALL_INTENT.search(question):
            self._log.info("context_agent.recall_answered",
                           question=question[:80], hits=len(recalled))
            answer = "From our earlier conversations:\n\n" + "\n\n---\n\n".join(
                r.content for r in recalled
            )
            return self._terminal(question, answer, "Recall",
                                  answer_data={"type": "memory_recall",
                                               "recalled": _recall_payload(recalled)})

        has_short_term = bool(context_turns)
        has_long_term = bool(recalled)

        # Nothing to resolve against — leave the question untouched.
        if not has_short_term and not has_long_term:
            return {"enriched_question": question}

        # With only same-conversation context and no recalled memory, skip the
        # enrichment LLM for long, marker-free questions (likely self-contained).
        if has_short_term and not has_long_term:
            if not _REFERENCE_MARKERS.search(question) and len(question.split()) > 7:
                return {"enriched_question": question}

        # Build the history block: recalled long-term memory + current window.
        blocks: list[str] = []
        if recalled:
            mem = "\n".join(f"- {r.content[:300]}" for r in recalled)
            blocks.append(f"Relevant earlier discussion (from past conversations):\n{mem}")
        if context_turns:
            recent = context_turns[-6:]
            hist = "\n".join(
                f"{t.get('role', 'user').upper()}: {str(t.get('content', ''))[:300]}"
                for t in recent
            )
            blocks.append(f"Current conversation:\n{hist}")
        history = "\n\n".join(blocks)

        user_msg = f"{history}\n\nNew question: {question}"
        enriched = await self._call_llm(
            system=_CONTEXT_SYSTEM,
            user=user_msg,
            max_tokens=256,
        )
        enriched = enriched.strip().strip('"').strip("'")
        if not enriched or len(enriched) < 3:
            enriched = question

        self._log.info(
            "context_agent.enriched",
            original=question[:80],
            enriched=enriched[:80],
            changed=(enriched.lower() != question.lower()),
            recalled=len(recalled),
        )

        result: dict[str, Any] = {"enriched_question": enriched}
        if recalled:
            result["lineage"] = {
                **(state.get("lineage") or {}),
                "recalled_memory": _recall_payload(recalled),
            }
        return result

    @staticmethod
    def _terminal(
        question: str, answer: str, intent: str, answer_data: dict | None = None
    ) -> dict[str, Any]:  # noqa: D401
        """Build a terminal state for questions answered directly from memory."""
        return {
            "enriched_question": question,
            "answer_text": answer,
            "answer_data": answer_data or {"type": "meta"},
            "chart_hint": "text",
            "follow_up_questions": [],
            "confidence_score": 1.0,
            "intent": intent,
        }

    @staticmethod
    def _answer_meta(question: str, context_turns: list[dict]) -> str | None:
        """Answer a question about the conversation itself from the Redis
        context window. Returns the answer text, or None if not a meta-question.

        context_turns holds prior turns only (the current turn isn't saved yet),
        as [{role: user|assistant, content}, ...] in chronological order.
        """
        def _last(role: str) -> str | None:
            for turn in reversed(context_turns):
                if turn.get("role") == role and turn.get("content"):
                    return str(turn["content"])
            return None

        if _META_PREV_QUESTION.search(question):
            prev = _last("user")
            return (
                f'Your previous question was: "{prev}"' if prev
                else "This is the first question in our conversation, so there is no previous one."
            )

        if _META_PREV_ANSWER.search(question):
            prev = _last("assistant")
            return (
                f"Here is what I said previously:\n\n{prev}" if prev
                else "I haven't given an answer yet in this conversation."
            )

        if _META_SUMMARY.search(question):
            questions = [
                str(t["content"]) for t in context_turns if t.get("role") == "user" and t.get("content")
            ]
            if not questions:
                return "We haven't discussed anything yet in this conversation."
            lines = "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1))
            return f"So far in this conversation you've asked:\n\n{lines}"

        return None


def _recall_payload(recalled: list) -> list[dict]:
    """Serialise recalled turns for answer_data / lineage."""
    return [
        {
            "conversation_id": str(r.conversation_id),
            "similarity": r.similarity,
            "content": r.content[:300],
        }
        for r in recalled
    ]
