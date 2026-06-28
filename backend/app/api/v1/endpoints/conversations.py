"""
Conversations REST API.

Endpoints:
  POST   /conversations                     — create a new conversation
  GET    /conversations                     — list user's conversations
  GET    /conversations/{id}                — get single conversation
  DELETE /conversations/{id}               — soft-delete conversation
  GET    /conversations/{id}/turns          — list turns in a conversation
  POST   /conversations/{id}/ask            — submit a question (graph entry point)
"""

from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_current_tenant
from app.schemas.conversation import (
    AskRequest,
    AskResponse,
    ConversationCreate,
    ConversationResponse,
    TurnResponse,
)
from app.services.conversation.manager import ConversationManager

router = APIRouter(prefix="/conversations", tags=["conversations"])


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: ConversationCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
    tenant=Depends(get_current_tenant),
):
    mgr = ConversationManager(db, tenant["id"])
    conv = await mgr.create_conversation(
        user_id=current_user.id,
        title=body.title,
        connection_id=body.connection_id,
    )
    return conv


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
    tenant=Depends(get_current_tenant),
    limit: int = 20,
    offset: int = 0,
):
    mgr = ConversationManager(db, tenant["id"])
    return await mgr.list_conversations(current_user.id, limit=limit, offset=offset)


# ── Get single ────────────────────────────────────────────────────────────────

@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
    tenant=Depends(get_current_tenant),
):
    mgr = ConversationManager(db, tenant["id"])
    conv = await mgr.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


# ── Soft-delete ───────────────────────────────────────────────────────────────

@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
    tenant=Depends(get_current_tenant),
):
    mgr = ConversationManager(db, tenant["id"])
    conv = await mgr.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv.is_active = False
    await db.commit()


# ── List turns ────────────────────────────────────────────────────────────────

@router.get("/{conversation_id}/turns", response_model=list[TurnResponse])
async def list_turns(
    conversation_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
    tenant=Depends(get_current_tenant),
):
    from sqlalchemy import select
    from app.models.conversation import ConversationTurn

    # Verify access
    mgr = ConversationManager(db, tenant["id"])
    conv = await mgr.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    result = await db.execute(
        select(ConversationTurn)
        .where(ConversationTurn.conversation_id == conversation_id)
        .order_by(ConversationTurn.turn_number)
    )
    return list(result.scalars().all())


# ── Truncate turns ─────────────────────────────────────────────────────────────

@router.delete("/{conversation_id}/turns/{turn_number}", status_code=status.HTTP_204_NO_CONTENT)
async def truncate_turns(
    conversation_id: uuid.UUID,
    turn_number: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
    tenant=Depends(get_current_tenant),
):
    mgr = ConversationManager(db, tenant["id"])
    conv = await mgr.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await mgr.truncate_turns(conversation_id, turn_number)


# ── ASK — graph entry point ───────────────────────────────────────────────────


@router.post("/{conversation_id}/ask", response_model=AskResponse)
async def ask(
    conversation_id: uuid.UUID,
    body: AskRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
    tenant=Depends(get_current_tenant),
):
    mgr = ConversationManager(db, tenant["id"])

    # Verify conversation exists
    conv = await mgr.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Build initial graph state
    turn_id = uuid.uuid4()
    initial_state = {
        "messages": [],
        "question": body.question,
        "tenant_id": tenant["id"],
        "user_id": current_user.id,
        "conversation_id": conversation_id,
        "turn_id": turn_id,
        "connection_id": body.connection_id,
        # Defaults — agents will fill these in
        "intent": None,
        "detected_domain": None,
        "enriched_question": None,
        "confidence": None,
        "candidate_tools": [],
        "selected_tool": None,
        "resolved_params": {},
        "join_path": None,
        "entity_ids": [],
        "sql_query": None,
        "query_result": None,
        "execution_time_ms": None,
        "answer_text": None,
        "answer_data": None,
        "chart_hint": None,
        "follow_up_questions": [],
        "lineage": None,
        "confidence_score": None,
        "error": None,
        "fallback_used": False,
        "agents_invoked": [],
        # Clarification (AG-007)
        "needs_clarification": False,
        "missing_params": [],
        "clarification_question": None,
    }

    # Run the agent graph
    from app.agents.supervisor import run_question
    final_state = await run_question(initial_state)

    # Extract results
    error_msg: str | None = final_state.get("error")
    tool = final_state.get("selected_tool") or {}
    tool_id_raw = tool.get("tool_id")
    tool_uuid = uuid.UUID(tool_id_raw) if tool_id_raw else None

    # Persist the turn
    turn = await mgr.save_turn(
        conversation_id=conversation_id,
        user_id=current_user.id,
        question=body.question,
        answer_text=final_state.get("answer_text"),
        answer_data=final_state.get("answer_data"),
        sql_query=final_state.get("sql_query"),
        chart_hint=final_state.get("chart_hint"),
        follow_up_questions=final_state.get("follow_up_questions") or [],
        lineage=final_state.get("lineage"),
        confidence_score=final_state.get("confidence_score"),
        execution_time_ms=final_state.get("execution_time_ms"),
        agents_invoked=final_state.get("agents_invoked") or [],
        intent=final_state.get("intent"),
        tool_id=tool_uuid,
        error=error_msg,
    )

    return AskResponse(
        turn_id=turn.id,
        conversation_id=conversation_id,
        question=body.question,
        answer_text=final_state.get("answer_text"),
        answer_data=final_state.get("answer_data"),
        sql_query=final_state.get("sql_query"),
        chart_hint=final_state.get("chart_hint"),
        follow_up_questions=final_state.get("follow_up_questions") or [],
        lineage=final_state.get("lineage"),
        confidence_score=final_state.get("confidence_score"),
        execution_time_ms=final_state.get("execution_time_ms"),
        agents_invoked=final_state.get("agents_invoked") or [],
        intent=final_state.get("intent"),
        has_error=bool(error_msg),
        error_message=error_msg,
        needs_clarification=bool(final_state.get("needs_clarification")),
        clarification_question=final_state.get("clarification_question"),
        missing_params=final_state.get("missing_params") or [],
    )


# ── ASK (streaming) — live reasoning as the agent thinks ──────────────────────

def _stream_step(node: str, state: dict) -> dict | None:
    """Map a just-completed graph node to a user-facing reasoning step. Returns
    None for nodes that shouldn't surface a step. Reads the accumulated state so
    each step reflects the real per-query decision (intent, tool, row count…)."""
    intent = state.get("intent")
    if node == "context_agent":
        if state.get("answer_text"):
            return {"node": node, "label": "Answered directly from our conversation."}
        return {"node": node, "label": "Understanding your question and context…"}
    if node == "intent_classifier":
        reasoning = state.get("reasoning")
        label = f"Recognised this as a {intent} question"
        label = f"{label} — {reasoning}" if reasoning else f"{label}."
        return {"node": node, "label": label, "intent": intent}
    if node == "query_planner":
        if state.get("use_text_to_sql") and not state.get("selected_tool"):
            return {"node": node, "label": "No prebuilt tool fit — generating SQL from your schema…"}
        tool_name = (state.get("selected_tool") or {}).get("name")
        if tool_name and tool_name != "ad_hoc_text_to_sql":
            return {"node": node, "label": f"Selected the '{tool_name}' analysis."}
        return {"node": node, "label": "Planning how to answer…"}
    if node == "text_to_sql":
        if state.get("selected_tool"):
            tables = (state.get("lineage") or {}).get("tables_used") or []
            tail = f" using {', '.join(tables)}" if tables else ""
            return {"node": node, "label": f"Generated a SQL query from your schema{tail}."}
        return None
    if node == "sql_executor":
        if state.get("needs_clarification"):
            return {"node": node, "label": "I need one detail to continue…"}
        row_count = (state.get("query_result") or {}).get("row_count")
        if row_count is not None:
            return {"node": node, "label": f"Queried the database — {row_count} row(s) returned."}
        return {"node": node, "label": "Querying the database…"}
    labels = {
        "response_formatter": "Composing the answer with key insights…",
        "rca_agent": "Running root-cause analysis…",
        "trend_agent": "Analysing the trend over time…",
        "hybrid_agent": "Blending data with document knowledge…",
        "document_rag": "Searching your documents…",
        "web_search": "Searching the web for current information…",
        "clarification_agent": "Preparing a clarifying question…",
        "error_handler": "Could not complete the request.",
    }
    if node in labels:
        return {"node": node, "label": labels[node]}
    return None


@router.post("/{conversation_id}/ask/stream")
async def ask_stream(
    conversation_id: uuid.UUID,
    body: AskRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
    tenant=Depends(get_current_tenant),
):
    """Same as /ask, but streams the agent's reasoning steps as NDJSON while it
    thinks, then persists the turn and emits a final `AskResponse` payload.

    Each line is one JSON object: {"type": "step", ...} during processing and a
    final {"type": "final", "data": {...}} at the end.
    """
    mgr = ConversationManager(db, tenant["id"])
    conv = await mgr.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    tenant_id = tenant["id"]
    user_id = current_user.id
    turn_id = uuid.uuid4()
    initial_state = {
        "messages": [],
        "question": body.question,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "turn_id": turn_id,
        "connection_id": body.connection_id,
        "intent": None,
        "detected_domain": None,
        "enriched_question": None,
        "confidence": None,
        "candidate_tools": [],
        "selected_tool": None,
        "resolved_params": {},
        "join_path": None,
        "entity_ids": [],
        "sql_query": None,
        "query_result": None,
        "execution_time_ms": None,
        "answer_text": None,
        "answer_data": None,
        "chart_hint": None,
        "follow_up_questions": [],
        "lineage": None,
        "confidence_score": None,
        "error": None,
        "fallback_used": False,
        "agents_invoked": [],
        "needs_clarification": False,
        "missing_params": [],
        "clarification_question": None,
    }

    async def generate():
        from app.agents.supervisor import get_graph
        from app.db.session import AsyncSessionLocal

        compiled = get_graph()
        acc: dict = dict(initial_state)
        try:
            async for chunk in compiled.astream(initial_state, stream_mode="updates"):
                for node, update in chunk.items():
                    if isinstance(update, dict):
                        acc.update(update)
                    step = _stream_step(node, acc)
                    if step:
                        yield json.dumps({"type": "step", **step}) + "\n"
        except Exception as exc:  # safety net — agents normally route errors in-state
            acc["error"] = str(exc)
            yield json.dumps(
                {"type": "step", "node": "error_handler", "label": "Could not complete the request."}
            ) + "\n"

        # Persist the turn in a fresh session (the request session is not used
        # during streaming).
        error_msg = acc.get("error")
        tool = acc.get("selected_tool") or {}
        tool_id_raw = tool.get("tool_id")
        tool_uuid = uuid.UUID(tool_id_raw) if tool_id_raw else None
        async with AsyncSessionLocal() as db2:
            turn = await ConversationManager(db2, tenant_id).save_turn(
                conversation_id=conversation_id,
                user_id=user_id,
                question=body.question,
                answer_text=acc.get("answer_text"),
                answer_data=acc.get("answer_data"),
                sql_query=acc.get("sql_query"),
                chart_hint=acc.get("chart_hint"),
                follow_up_questions=acc.get("follow_up_questions") or [],
                lineage=acc.get("lineage"),
                confidence_score=acc.get("confidence_score"),
                execution_time_ms=acc.get("execution_time_ms"),
                agents_invoked=acc.get("agents_invoked") or [],
                intent=acc.get("intent"),
                tool_id=tool_uuid,
                error=error_msg,
            )

        final = {
            "turn_id": str(turn.id),
            "conversation_id": str(conversation_id),
            "question": body.question,
            "answer_text": acc.get("answer_text"),
            "answer_data": acc.get("answer_data"),
            "sql_query": acc.get("sql_query"),
            "chart_hint": acc.get("chart_hint"),
            "follow_up_questions": acc.get("follow_up_questions") or [],
            "lineage": acc.get("lineage"),
            "confidence_score": acc.get("confidence_score"),
            "execution_time_ms": acc.get("execution_time_ms"),
            "agents_invoked": acc.get("agents_invoked") or [],
            "intent": acc.get("intent"),
            "has_error": bool(error_msg),
            "error_message": error_msg,
            "needs_clarification": bool(acc.get("needs_clarification")),
            "clarification_question": acc.get("clarification_question"),
            "missing_params": acc.get("missing_params") or [],
        }
        yield json.dumps({"type": "final", "data": final}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")
