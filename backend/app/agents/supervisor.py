"""
LangGraph graph wiring — routes questions through the multi-agent pipeline.

Spec: AG-001, AG-002

Graph topology (Sprint 9):
  entry
    └─> context_agent              (resolves pronouns/references from prior turns)
          └─> intent_classifier    (Lookup|Aggregation|Trend|Comparative|RCA|Document|Hybrid|Web)
                ├─[Document]──────> document_rag ─> END
                ├─[Web]────────────> web_search ─> END
                ├─[RCA]────────────> query_planner ─> sql_executor ─> rca_agent ─> END
                ├─[Trend]──────────> query_planner ─> sql_executor ─> trend_agent ─> END
                ├─[Hybrid]─────────> query_planner ─> sql_executor ─> response_formatter
                │                         └─> hybrid_agent ─> END
                └─[other]──────────> query_planner
                                        ├─[no tool]─────> text_to_sql ─> sql_executor
                                        └─> sql_executor
                                              ├─[clarification]─> clarification_agent ─> END
                                              ├─[error]─────────> error_handler ─> END
                                              └─[ok]────────────> response_formatter ─> END

Compiled graph is cached as a module-level singleton (lru_cache(maxsize=1)).
Call get_graph.cache_clear() in tests to rebuild.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from langgraph.graph import END, StateGraph

from app.agents.state import AgentState
from app.agents.context_agent import ContextAgent
from app.agents.intent_classifier import IntentClassifierAgent
from app.agents.query_planner import QueryPlannerAgent
from app.agents.sql_executor import SQLExecutorAgent
from app.agents.response_formatter import ResponseFormatterAgent
from app.agents.clarification_agent import ClarificationAgent
from app.agents.document_rag import DocumentRAGAgent
from app.agents.rca_agent import RCAAgent
from app.agents.trend_agent import TrendAgent
from app.agents.hybrid_agent import HybridAgent
from app.agents.web_search import WebSearchAgent
from app.agents.text_to_sql import TextToSQLAgent

# ── Agent singletons ─────────────────────────────────────────────────────────

_context_agent = ContextAgent()
_intent_classifier = IntentClassifierAgent()
_query_planner = QueryPlannerAgent()
_text_to_sql = TextToSQLAgent()
_sql_executor = SQLExecutorAgent()
_response_formatter = ResponseFormatterAgent()
_clarification_agent = ClarificationAgent()
_document_rag = DocumentRAGAgent()
_rca_agent = RCAAgent()
_trend_agent = TrendAgent()
_hybrid_agent = HybridAgent()
_web_search = WebSearchAgent()


# ── Error handler ─────────────────────────────────────────────────────────────

async def _error_handler(state: AgentState) -> dict[str, Any]:
    error_msg = state.get("error", "An unexpected error occurred.")
    return {
        "answer_text": (
            f"I was unable to answer your question. {error_msg} "
            "Please try rephrasing or contact your administrator."
        ),
        "answer_data": {"error": error_msg},
        "chart_hint": "table",
        "follow_up_questions": [],
        "confidence_score": 0.0,
        "lineage": None,
    }


# ── Conditional routing ───────────────────────────────────────────────────────

def _route_after_context(state: AgentState) -> str:
    if state.get("error"):
        return "error_handler"
    # Meta-questions about the conversation are answered in context_agent
    # directly from history — skip the data pipeline.
    if state.get("answer_text"):
        return END
    return "intent_classifier"


def _route_after_intent(state: AgentState) -> str:
    if state.get("error"):
        return "error_handler"
    intent = state.get("intent")
    if intent == "Document":
        return "document_rag"
    if intent == "Web":
        return "web_search"
    # All other intents (including RCA, Hybrid) go through query_planner first
    return "query_planner"


def _route_after_planner(state: AgentState) -> str:
    if state.get("error"):
        return "error_handler"
    if not state.get("selected_tool"):
        # No curated tool matched — fall back to the text-to-SQL agent, which
        # generates a SELECT from the crawled schema catalog.
        if state.get("use_text_to_sql"):
            return "text_to_sql"
        return "error_handler"
    return "sql_executor"


def _route_after_text_to_sql(state: AgentState) -> str:
    if state.get("error"):
        return "error_handler"
    if state.get("selected_tool"):
        return "sql_executor"
    return "error_handler"


def _route_after_executor(state: AgentState) -> str:
    if state.get("error"):
        return "error_handler"
    if state.get("needs_clarification"):
        return "clarification_agent"
    intent = state.get("intent")
    if intent == "RCA":
        return "rca_agent"
    if intent == "Trend":
        return "trend_agent"
    return "response_formatter"


def _route_after_formatter(state: AgentState) -> str:
    if state.get("intent") == "Hybrid":
        return "hybrid_agent"
    return END


# ── Graph factory ─────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_graph():
    """
    Build and compile the LangGraph StateGraph.
    Cached so compile() runs only once per process lifecycle.
    Call get_graph.cache_clear() in tests to rebuild.
    """
    graph = StateGraph(AgentState)

    # Register nodes
    graph.add_node("context_agent", _context_agent)
    graph.add_node("intent_classifier", _intent_classifier)
    graph.add_node("query_planner", _query_planner)
    graph.add_node("text_to_sql", _text_to_sql)
    graph.add_node("sql_executor", _sql_executor)
    graph.add_node("response_formatter", _response_formatter)
    graph.add_node("clarification_agent", _clarification_agent)
    graph.add_node("document_rag", _document_rag)
    graph.add_node("rca_agent", _rca_agent)
    graph.add_node("trend_agent", _trend_agent)
    graph.add_node("hybrid_agent", _hybrid_agent)
    graph.add_node("web_search", _web_search)
    graph.add_node("error_handler", _error_handler)

    # Entry point
    graph.set_entry_point("context_agent")

    # Routing edges
    graph.add_conditional_edges(
        "context_agent",
        _route_after_context,
        {"intent_classifier": "intent_classifier", "error_handler": "error_handler", END: END},
    )

    graph.add_conditional_edges(
        "intent_classifier",
        _route_after_intent,
        {
            "query_planner": "query_planner",
            "document_rag": "document_rag",
            "web_search": "web_search",
            "error_handler": "error_handler",
        },
    )

    graph.add_conditional_edges(
        "query_planner",
        _route_after_planner,
        {
            "sql_executor": "sql_executor",
            "text_to_sql": "text_to_sql",
            "error_handler": "error_handler",
        },
    )

    graph.add_conditional_edges(
        "text_to_sql",
        _route_after_text_to_sql,
        {"sql_executor": "sql_executor", "error_handler": "error_handler"},
    )

    graph.add_conditional_edges(
        "sql_executor",
        _route_after_executor,
        {
            "response_formatter": "response_formatter",
            "clarification_agent": "clarification_agent",
            "rca_agent": "rca_agent",
            "trend_agent": "trend_agent",
            "error_handler": "error_handler",
        },
    )

    graph.add_conditional_edges(
        "response_formatter",
        _route_after_formatter,
        {"hybrid_agent": "hybrid_agent", END: END},
    )

    # Terminal edges
    graph.add_edge("clarification_agent", END)
    graph.add_edge("rca_agent", END)
    graph.add_edge("trend_agent", END)
    graph.add_edge("hybrid_agent", END)
    graph.add_edge("document_rag", END)
    graph.add_edge("web_search", END)
    graph.add_edge("error_handler", END)

    return graph.compile()


async def run_question(initial_state: dict[str, Any]) -> AgentState:
    """Invoke the compiled graph and return final state."""
    compiled = get_graph()
    return await compiled.ainvoke(initial_state)
