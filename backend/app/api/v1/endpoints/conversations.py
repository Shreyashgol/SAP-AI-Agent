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

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
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
