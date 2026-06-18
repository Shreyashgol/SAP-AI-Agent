"""
Regression tests for conversation-memory fixes.

Covers:
  - ContextAgent._answer_meta: meta-questions about the conversation are answered
    from the Redis context window (previous question/answer, recap) instead of
    being mis-rewritten into a data query.
  - Reference markers: short follow-ups ("what about the lowest one?", "the top
    one") are recognised so they get context-enriched.
"""

import pytest
from unittest.mock import AsyncMock

from app.agents.context_agent import (
    ContextAgent,
    _REFERENCE_MARKERS,
    _META_PREV_QUESTION,
    _META_SUMMARY,
    _META_COUNT,
    _ASSIST_IDENTITY,
    _ASSIST_CAPABILITY,
    _GREETING,
    _COURTESY,
    _RECALL_INTENT,
)
from app.services.conversation.memory import ConversationMemoryService


_HISTORY = [
    {"role": "user", "content": "What were total sales by city?"},
    {"role": "assistant", "content": "Bangalore led with $300,000..."},
    {"role": "user", "content": "Show me total invoiced sales for 2025."},
    {"role": "assistant", "content": "Total invoiced sales for 2025 are $870,000."},
]


# ── Meta-question handling ────────────────────────────────────────────────────

@pytest.mark.unit
def test_meta_previous_question_returns_last_user_turn():
    ans = ContextAgent._answer_meta("What was my previous question?", _HISTORY)
    assert ans is not None
    assert "Show me total invoiced sales for 2025." in ans


@pytest.mark.unit
def test_meta_previous_answer_returns_last_assistant_turn():
    ans = ContextAgent._answer_meta("What did you just say?", _HISTORY)
    assert ans is not None
    assert "$870,000" in ans


@pytest.mark.unit
def test_meta_summary_lists_prior_questions():
    ans = ContextAgent._answer_meta("Summarize our conversation so far", _HISTORY)
    assert ans is not None
    assert "total sales by city" in ans.lower()
    assert "invoiced sales for 2025" in ans.lower()


@pytest.mark.unit
def test_non_meta_question_returns_none():
    assert ContextAgent._answer_meta("What were total sales by city?", _HISTORY) is None


@pytest.mark.unit
def test_meta_previous_question_with_no_history():
    ans = ContextAgent._answer_meta("what did I ask?", [])
    assert ans is not None
    assert "first question" in ans.lower()


# ── Conversational / "human" questions (greeting, identity, capability, count) ─

@pytest.mark.unit
@pytest.mark.parametrize("q", [
    "How many questions have I asked till now?",
    "how many questions did I ask?",
    "What is the number of questions I have asked?",
    "how many times have I asked you something?",
])
def test_count_questions_match(q):
    assert _META_COUNT.search(q) is not None


@pytest.mark.unit
@pytest.mark.parametrize("q", [
    "How many invoices did customer C20000 raise?",
    "How many open sales orders are there?",
    "Number of items below reorder level?",
])
def test_count_questions_do_not_match_data(q):
    assert _META_COUNT.search(q) is None


@pytest.mark.unit
@pytest.mark.parametrize("q", [
    "Who are you?",
    "what are you?",
    "What's your name?",
    "Are you a bot?",
    "introduce yourself",
])
def test_identity_questions_match(q):
    assert _ASSIST_IDENTITY.search(q) is not None


@pytest.mark.unit
@pytest.mark.parametrize("q", [
    "What can you do?",
    "what can I ask?",
    "what kind of questions can I ask you?",
    "How can you help me?",
    "how does this work?",
])
def test_capability_questions_match(q):
    assert _ASSIST_CAPABILITY.search(q) is not None


@pytest.mark.unit
@pytest.mark.parametrize("q", [
    "hi", "Hello!", "hey", "good morning", "how are you?", "what's up",
])
def test_greetings_match(q):
    assert _GREETING.match(q) is not None


@pytest.mark.unit
@pytest.mark.parametrize("q", [
    "Show me hi-value invoices",       # 'hi' as a substring must not match
    "What were total sales by city?",
    "hello world report for sales",
])
def test_greetings_do_not_match_data(q):
    assert _GREETING.match(q) is None


@pytest.mark.unit
@pytest.mark.parametrize("q", ["thanks", "thank you so much!", "great", "bye"])
def test_courtesy_match(q):
    assert _COURTESY.match(q) is not None


# ── Grounded LLM phrasing for conversational replies ──────────────────────────

@pytest.mark.unit
async def test_phrase_uses_llm_output():
    agent = ContextAgent()
    agent._call_llm = AsyncMock(return_value="  Hey! Ask me about your sales. ")
    out = await agent._phrase("greet the user", fallback="FB")
    assert out == "Hey! Ask me about your sales."


@pytest.mark.unit
async def test_phrase_falls_back_when_llm_fails():
    agent = ContextAgent()
    agent._call_llm = AsyncMock(side_effect=RuntimeError("provider down"))
    out = await agent._phrase("greet the user", fallback="FALLBACK-TEXT")
    assert out == "FALLBACK-TEXT"


@pytest.mark.unit
async def test_greeting_answer_is_llm_phrased():
    agent = ContextAgent()
    agent._call_llm = AsyncMock(return_value="Hello there, what would you like to know?")
    res = await agent._answer_conversational("hi", [], "cid", None, "tid")
    assert res is not None
    label, text, data = res
    assert label == "Smalltalk"
    assert text == "Hello there, what would you like to know?"
    agent._call_llm.assert_awaited_once()


@pytest.mark.unit
async def test_capability_answer_is_grounded_and_llm_phrased():
    agent = ContextAgent()
    agent._capability_grounding = AsyncMock(return_value="Business areas: sales, inventory.")
    agent._call_llm = AsyncMock(return_value="I can analyse your sales and inventory.")
    res = await agent._answer_conversational("what can you do?", [], "cid", "uid", "tid")
    assert res is not None
    label, text, data = res
    assert label == "Assistant"
    assert text == "I can analyse your sales and inventory."
    agent._capability_grounding.assert_awaited_once()
    # The grounding text must be fed into the LLM prompt.
    prompt = agent._call_llm.await_args.kwargs["user"]
    assert "Business areas: sales, inventory." in prompt


@pytest.mark.unit
async def test_capability_grounding_falls_back_with_no_tools(monkeypatch):
    agent = ContextAgent()

    class _FakeResult:
        def all(self):
            return []

    class _FakeDB:
        async def execute(self, *a, **k):
            return _FakeResult()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False

    import app.db.session as sess
    monkeypatch.setattr(sess, "AsyncSessionLocal", lambda: _FakeDB())
    out = await agent._capability_grounding("tid")
    assert "General SAP Business One analytics" in out


@pytest.mark.unit
async def test_data_question_passes_through_conversational():
    agent = ContextAgent()
    agent._call_llm = AsyncMock(return_value="should-not-be-called")
    res = await agent._answer_conversational(
        "What were total sales by city?", [], "cid", "uid", "tid"
    )
    assert res is None
    agent._call_llm.assert_not_awaited()


# ── Broadened reference markers for short follow-ups ──────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("q", [
    "Now show me just the top 3 of those.",
    "What about the lowest one?",
    "How many invoices did the top one have?",
    "Drill into that.",
])
def test_followups_are_flagged_for_enrichment(q):
    assert _REFERENCE_MARKERS.search(q) is not None


# ── Long-term / cross-conversation recall ─────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("q", [
    "What did we discuss about sales by city earlier?",
    "Remind me what we found about inventory.",
    "Did we look at Delhi last time?",
    "You told me the revenue figure before.",
])
def test_recall_intent_matches_memory_questions(q):
    assert _RECALL_INTENT.search(q) is not None


@pytest.mark.unit
@pytest.mark.parametrize("q", [
    "How many open sales orders are there?",
    "What is total revenue for 2025?",
    "Show me the top customers by sales.",
])
def test_recall_intent_does_not_match_data_questions(q):
    assert _RECALL_INTENT.search(q) is None


@pytest.mark.unit
def test_memory_build_content_includes_question_and_answer():
    content = ConversationMemoryService._build_content(
        "What were sales by city?", "Bangalore led with $300,000."
    )
    assert "Q: What were sales by city?" in content
    assert "A: Bangalore led with $300,000." in content


@pytest.mark.unit
def test_memory_build_content_handles_missing_answer():
    content = ConversationMemoryService._build_content("Any sales?", None)
    assert content == "Q: Any sales?"
