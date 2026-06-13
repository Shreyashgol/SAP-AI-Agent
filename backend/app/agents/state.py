"""
LangGraph agent state — shared context threaded through all agents.

Spec: AG-001, AG-002
The AgentState TypedDict is the single source of truth passed between graph nodes.
Each agent reads what it needs and writes its output fields only.

Immutability contract:
  - question, tenant_id, user_id, conversation_id, turn_id are set at graph entry and never mutated
  - agents APPEND to messages (never replace)
  - error is set once by the error-handler node; other agents check it before running

Intent values (AG-003):
  Lookup | Aggregation | Trend | Comparative | RCA | Document | Hybrid

Chart hint values:
  bar | line | area | donut | waterfall | kpi_card | table
"""

from __future__ import annotations

import uuid
from typing import Any, TypedDict

from langgraph.graph import MessagesState


class AgentState(MessagesState):
    """Shared state threaded through all graph nodes."""

    # ── Input (immutable after graph entry) ──────────────────────────────────
    question: str
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    conversation_id: uuid.UUID
    turn_id: uuid.UUID
    connection_id: uuid.UUID | None  # primary DB connection to query

    # ── Intent classification (AG-003) ───────────────────────────────────────
    intent: str | None                     # Lookup | Aggregation | Trend | ...
    detected_domain: str | None            # finance | sales | ...
    enriched_question: str | None          # context-resolved question (Sprint 7)
    confidence: float | None               # 0–1 classification confidence

    # ── Query planning (AG-004) ──────────────────────────────────────────────
    candidate_tools: list[dict[str, Any]]  # [{tool_id, name, score, params}]
    selected_tool: dict[str, Any] | None   # resolved tool with bound params
    resolved_params: dict[str, Any]        # :param_name → value map
    join_path: str | None                  # SQL JOIN chain from KG traversal
    entity_ids: list[uuid.UUID]            # resolved entity IDs for the query

    # ── SQL execution (AG-005) ───────────────────────────────────────────────
    sql_query: str | None                  # final parameterised SQL
    query_result: dict[str, Any] | None    # {rows, columns, row_count, truncated}
    execution_time_ms: int | None

    # ── Response formatting (AG-006) ────────────────────────────────────────
    answer_text: str | None
    answer_data: dict[str, Any] | None     # structured payload for UI
    chart_hint: str | None
    follow_up_questions: list[str]
    lineage: dict[str, Any] | None         # {tool, tables, entities, turn_id}
    confidence_score: float | None         # final answer confidence 0–1

    # ── Clarification (AG-007) ───────────────────────────────────────────────
    needs_clarification: bool              # True when required params are missing
    missing_params: list[str]             # param names the user must supply
    clarification_question: str | None    # natural-language prompt to show user

    # ── Error handling ───────────────────────────────────────────────────────
    error: str | None
    fallback_used: bool                    # True if a fallback path was taken
    agents_invoked: list[str]              # ordered list of node names run
