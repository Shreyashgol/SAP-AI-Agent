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

from app.agents.context_agent import (
    ContextAgent,
    _REFERENCE_MARKERS,
    _META_PREV_QUESTION,
    _META_SUMMARY,
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
