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
# "How many questions have I asked?" — answered from the real turn count, not data.
_META_COUNT = re.compile(
    r"\bhow many (questions|queries|times)\b"
    r"|\bnumber of (questions|queries)\b"
    r"|\bhow many (have|did) i ask"
    r"|\bhow many times (have|did) i\b",
    re.IGNORECASE,
)

# "Human"/conversational questions about the assistant itself (answered directly,
# never sent to the SQL pipeline). These keep the SAP B1 identity — this is a
# multi-talent SAP B1 agent, not a generic chatbot.
_ASSIST_IDENTITY = re.compile(
    r"\b(who are you|what are you|what'?s your name|your name"
    r"|are you (a |an )?(bot|ai|human|robot|chatbot|assistant|person|machine)"
    r"|introduce yourself|tell me about yourself|who am i (talking|chatting) (to|with))\b",
    re.IGNORECASE,
)
_ASSIST_CAPABILITY = re.compile(
    r"\b(what can you (do|help)|what can i ask"
    r"|what (kinds?|types?) of (questions|things) can (i|you)"
    r"|what are you (capable|able) of|how can you help"
    r"|how do(es)? (you|this) work|what do you do)\b",
    re.IGNORECASE,
)
# Greetings / courtesy — matched only when the WHOLE message is one (anchored ^…$)
# so they never fire inside a real data question like "say hi to customer X".
_GREETING = re.compile(
    r"^(hi+|hey+|hello+|yo|hiya|howdy|heya|"
    r"good (morning|afternoon|evening|day)|greetings|namaste|"
    r"how are you( doing)?|how'?s it going|what'?s up|sup)[\s!.?,]*$",
    re.IGNORECASE,
)
_COURTESY = re.compile(
    r"^(thanks?|thank you( so much)?|thx|ty|cheers|appreciate it|"
    r"great|awesome|cool|nice|perfect|ok(ay)?|got it|understood|"
    r"bye|goodbye|see you|see ya|good night)[\s!.?,]*$",
    re.IGNORECASE,
)

# Conversational replies are phrased by the LLM (grounded in the real tool
# catalog), so they sound natural and vary — not canned. These constants are
# only the graceful fallback when the LLM call fails (e.g. provider error), so
# the user always gets a sensible answer.
_CONVO_SYSTEM = """\
You are the user-facing voice of an SAP Business One analytics assistant — a
multi-talent agent that answers business questions over the user's real SAP B1
data (sales, inventory, finance, purchasing, operations), handles follow-ups,
and remembers context across the conversation.

Reply to the user's conversational message naturally, warmly and concisely
(2–4 sentences; a short bulleted list is fine when explaining capabilities).
Stay in character as this SAP B1 assistant — do NOT behave like a generic
chatbot and do NOT claim abilities outside business-data analysis. If GROUNDING
facts are provided, describe only what they support; never invent tools, data,
or numbers. When it fits, end by inviting a concrete data question. Output plain
text only (light Markdown for bullets is fine)."""

_FALLBACK_IDENTITY = (
    "I'm your SAP Business One AI assistant. I connect directly to your SAP B1 "
    "data and answer business questions in plain language — across sales, "
    "inventory, finance, purchasing and operations — and I remember the context "
    "of our conversation so you can ask natural follow-ups."
)
_FALLBACK_CAPABILITY = (
    "I can help you explore and analyse your SAP Business One data — lookups, "
    "totals and KPIs, trends, comparisons and root-cause analysis, plus questions "
    "over your uploaded documents and the latest SAP updates from the web. "
    "I also remember what we've discussed, so you can ask follow-ups like "
    "\"now break that down by city\". What would you like to know?"
)
_FALLBACK_GREETING = (
    "Hello! I'm your SAP Business One assistant. Ask me anything about your "
    "sales, inventory, finance or purchasing data — for example, \"total sales "
    "this month\" or \"top 5 customers by revenue\"."
)
_FALLBACK_COURTESY = (
    "You're welcome! Let me know if there's anything else about your SAP B1 data "
    "I can help with."
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
- If the latest user message ANSWERS a clarifying question the assistant just
  asked, rewrite it as the user's ORIGINAL question (from earlier in the history)
  with the newly supplied detail filled in. Preserve the original intent and ALL
  references it made — especially mentions of a policy, document, or guideline
  (e.g. "our credit policy", "the payment terms in our policy").
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

        # Conversational / "human" questions (greetings, identity, capabilities,
        # how-many-questions, previous question/answer, recap) are answered here
        # directly, short-circuiting the data pipeline (supervisor routes to END
        # when answer_text is set). This works even on the first turn (no prior
        # context) — otherwise "how many questions have I asked?" or "who are
        # you?" would fall through to the SQL planner and error out with
        # "no tool matches against the available data".
        conv = await self._answer_conversational(
            question, context_turns, conversation_id, user_id, state["tenant_id"]
        )
        if conv is not None:
            intent_label, text, data = conv
            self._log.info(
                "context_agent.conversational_answered",
                question=question[:80], kind=intent_label,
            )
            return self._terminal(question, text, intent_label, answer_data=data)

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

        # A clarification follow-up: the previous assistant turn was a clarifying
        # question (ends with "?"), so this message answers it. Always enrich so it
        # is rewritten back into the original question (which may be Hybrid/RCA/etc.)
        # with the new detail filled in — otherwise the bare answer gets re-classified
        # as a plain Aggregation and loses the original intent (e.g. policy blend).
        last_assistant = next(
            (str(t.get("content", "")) for t in reversed(context_turns)
             if t.get("role") == "assistant"),
            "",
        )
        is_clarification_followup = last_assistant.strip().endswith("?")

        # With only same-conversation context and no recalled memory, skip the
        # enrichment LLM for long, marker-free questions (likely self-contained) —
        # but never skip a clarification follow-up.
        if has_short_term and not has_long_term and not is_clarification_followup:
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

    async def _answer_conversational(
        self,
        question: str,
        context_turns: list[dict],
        conversation_id: Any,
        user_id: Any,
        tenant_id: Any,
    ) -> tuple[str, str, dict] | None:
        """Answer a conversational / "human" question about the assistant or the
        conversation itself. Returns (intent_label, answer_text, answer_data) or
        None when the question is a genuine data question to pass through.
        """
        q = question.strip()
        is_help = q.lower().strip(" !.?") == "help"

        # Whole-message greetings / courtesy (anchored so they don't fire inside
        # a real data question). Phrasing comes from the LLM so it sounds natural.
        if _GREETING.match(q):
            text = await self._phrase(
                f'The user greeted you with: "{q}". Greet them back briefly and '
                f"invite a concrete data question.",
                _FALLBACK_GREETING,
            )
            return ("Smalltalk", text, {"type": "smalltalk"})
        if _COURTESY.match(q):
            text = await self._phrase(
                f'The user said: "{q}" (a thanks or sign-off). Acknowledge it '
                f"briefly and warmly, and offer further help.",
                _FALLBACK_COURTESY,
            )
            return ("Smalltalk", text, {"type": "smalltalk"})

        # Who/what are you, what can you do — grounded in the real tool catalog so
        # the answer reflects what this connection can actually do.
        if _ASSIST_IDENTITY.search(q):
            grounding = await self._capability_grounding(tenant_id)
            text = await self._phrase(
                f'The user asked who or what you are: "{q}". Introduce yourself in '
                f"2–3 sentences.\n\nGROUNDING (capabilities on this connection):\n{grounding}",
                _FALLBACK_IDENTITY,
            )
            return ("Assistant", text, {"type": "assistant"})
        if _ASSIST_CAPABILITY.search(q) or is_help:
            grounding = await self._capability_grounding(tenant_id)
            text = await self._phrase(
                f'The user asked what you can do: "{q}". Briefly explain how you can '
                f"help, then give a few concrete example questions they could ask.\n\n"
                f"GROUNDING (capabilities on this connection):\n{grounding}",
                _FALLBACK_CAPABILITY,
            )
            return ("Assistant", text, {"type": "assistant"})

        # "How many questions have I asked?" — answered from the real turn count.
        if _META_COUNT.search(q):
            text = await self._answer_count(conversation_id, user_id, tenant_id)
            return ("Meta", text, {"type": "meta"})

        # Previous question / answer / recap — needs the short-term window.
        if context_turns:
            meta = self._answer_meta(q, context_turns)
            if meta is not None:
                return ("Meta", meta, {"type": "meta"})

        return None

    async def _phrase(self, instruction: str, fallback: str) -> str:
        """Phrase a conversational reply with the LLM, grounded by `instruction`.
        Falls back to a sensible canned reply if the LLM call fails so the user
        always gets an answer."""
        try:
            out = (
                await self._call_llm(
                    system=_CONVO_SYSTEM, user=instruction, max_tokens=400
                )
            ).strip()
            return out or fallback
        except Exception as exc:
            self._log.warning("context_agent.phrase_fail", exc=str(exc))
            return fallback

    async def _capability_grounding(self, tenant_id: Any) -> str:
        """Summarise the tenant's real active tools (name/domain/description) so
        identity/capability answers describe what this connection can actually
        do, instead of a hardcoded list that can drift from the schema."""
        from sqlalchemy import select
        from app.db.session import AsyncSessionLocal
        from app.models.tool import Tool

        rows: list[Any] = []
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Tool.name, Tool.description, Tool.domain)
                    .where(Tool.tenant_id == tenant_id, Tool.status == "active")
                    .order_by(Tool.domain)
                    .limit(40)
                )
                rows = list(result.all())
        except Exception as exc:
            self._log.warning("context_agent.grounding_fail", exc=str(exc))

        if not rows:
            return (
                "General SAP Business One analytics: lookups, totals/KPIs, trends, "
                "comparisons and root-cause analysis, plus document and web questions. "
                "(No specific tool catalog is available for this connection yet.)"
            )

        domains = sorted({r.domain for r in rows if r.domain})
        lines = [
            f"- {r.name} ({r.domain}): {(r.description or '')[:120]}" for r in rows[:15]
        ]
        return (
            f"Business areas covered: {', '.join(domains)}.\n"
            f"Example capabilities (tools):\n" + "\n".join(lines)
        )

    async def _answer_count(
        self, conversation_id: Any, user_id: Any, tenant_id: Any
    ) -> str:
        """Count the user's questions accurately from the database (the Redis
        window only holds the last N turns). The current question isn't persisted
        yet, so it's added on top of the stored count.
        """
        from sqlalchemy import select, func
        from app.db.session import AsyncSessionLocal
        from app.models.conversation import ConversationTurn

        prior = 0
        lifetime = 0
        try:
            async with AsyncSessionLocal() as db:
                prior = (
                    await db.execute(
                        select(func.count(ConversationTurn.id)).where(
                            ConversationTurn.conversation_id == conversation_id
                        )
                    )
                ).scalar() or 0
                if user_id:
                    lifetime = (
                        await db.execute(
                            select(func.count(ConversationTurn.id)).where(
                                ConversationTurn.tenant_id == tenant_id,
                                ConversationTurn.user_id == user_id,
                            )
                        )
                    ).scalar() or 0
        except Exception as exc:
            self._log.warning("context_agent.count_fail", exc=str(exc))

        current = prior + 1  # include the question being asked right now
        if prior == 0:
            return "This is the first question you've asked in this conversation."
        msg = (
            f"You've asked {current} questions so far in this conversation "
            f"(including this one)."
        )
        total = lifetime + 1
        if total > current:
            msg += f" Across all your conversations, that's {total} in total."
        return msg

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
