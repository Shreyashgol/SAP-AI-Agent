import pytest
import uuid
from sqlalchemy import select
from unittest.mock import AsyncMock, MagicMock
from app.services.conversation.manager import ConversationManager
from app.models.conversation import Conversation, ConversationTurn, ConversationTurnEmbedding
from app.models.tenant import Tenant
from app.models.user import User

@pytest.mark.asyncio
async def test_truncate_turns(db_session, fake_redis, monkeypatch):
    # Mock redis context update/rebuild dependencies if get_redis is used
    import app.core.redis as redis_mod
    monkeypatch.setattr(redis_mod, "get_redis", lambda: fake_redis)

    # Mock get_embedding_client to return a fake embedding client
    import app.services.embedding.client as embed_mod
    mock_client = MagicMock()
    mock_client.embed_single = AsyncMock(return_value=[0.1] * 1024)
    monkeypatch.setattr(embed_mod, "get_embedding_client", lambda: mock_client)

    # Create dummy Tenant and User
    tenant = Tenant(name="Test Corp", slug=f"test-{uuid.uuid4().hex[:8]}", timezone="UTC")
    db_session.add(tenant)
    await db_session.flush()

    user = User(
        tenant_id=tenant.id,
        email="admin@test.com",
        full_name="Test Admin",
        hashed_password="...",
    )
    db_session.add(user)
    await db_session.flush()

    mgr = ConversationManager(db_session, tenant.id)
    
    # 1. Create a conversation
    conv = await mgr.create_conversation(user_id=user.id, title="Test Conversation")
    
    # 2. Add some turns
    turn1 = await mgr.save_turn(
        conversation_id=conv.id,
        user_id=user.id,
        question="Turn 1",
        answer_text="Ans 1",
        answer_data=None,
        sql_query=None,
        chart_hint=None,
        follow_up_questions=[],
        lineage=None,
        confidence_score=0.9,
        execution_time_ms=100,
        agents_invoked=[],
    )

    turn2 = await mgr.save_turn(
        conversation_id=conv.id,
        user_id=user.id,
        question="Turn 2",
        answer_text="Ans 2",
        answer_data=None,
        sql_query=None,
        chart_hint=None,
        follow_up_questions=[],
        lineage=None,
        confidence_score=0.9,
        execution_time_ms=100,
        agents_invoked=[],
    )

    turn3 = await mgr.save_turn(
        conversation_id=conv.id,
        user_id=user.id,
        question="Turn 3",
        answer_text="Ans 3",
        answer_data=None,
        sql_query=None,
        chart_hint=None,
        follow_up_questions=[],
        lineage=None,
        confidence_score=0.9,
        execution_time_ms=100,
        agents_invoked=[],
    )

    # Verify database has 3 turns and 3 embeddings
    turns_res = await db_session.execute(
        select(ConversationTurn).where(ConversationTurn.conversation_id == conv.id)
    )
    assert len(turns_res.scalars().all()) == 3

    embeddings_res = await db_session.execute(
        select(ConversationTurnEmbedding).where(ConversationTurnEmbedding.conversation_id == conv.id)
    )
    assert len(embeddings_res.scalars().all()) == 3

    # 3. Truncate from turn 2 onwards
    await mgr.truncate_turns(conv.id, 2)

    # 4. Verify turn 2 and 3 are deleted, turn 1 remains
    turns_res = await db_session.execute(
        select(ConversationTurn).where(ConversationTurn.conversation_id == conv.id)
    )
    remaining_turns = turns_res.scalars().all()
    assert len(remaining_turns) == 1
    assert remaining_turns[0].turn_number == 1
    assert remaining_turns[0].question == "Turn 1"

    # Verify embeddings are deleted
    embeddings_res = await db_session.execute(
        select(ConversationTurnEmbedding).where(ConversationTurnEmbedding.conversation_id == conv.id)
    )
    remaining_embeddings = embeddings_res.scalars().all()
    assert len(remaining_embeddings) == 1
    assert remaining_embeddings[0].turn_id == turn1.id

    # Verify conv.turn_count is updated
    await db_session.refresh(conv)
    assert conv.turn_count == 1
