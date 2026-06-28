import pytest
import uuid
from sqlalchemy import select
from unittest.mock import AsyncMock, MagicMock
from app.api.deps import get_current_user, get_current_tenant
from app.main import app
from app.models.tenant import Tenant
from app.models.user import User
from app.models.conversation import Conversation, ConversationTurn
from app.services.conversation.manager import ConversationManager

@pytest.mark.asyncio
async def test_delete_turns_endpoint(client, db_session, fake_redis, monkeypatch):
    # Mock redis context update/rebuild dependencies
    import app.core.redis as redis_mod
    monkeypatch.setattr(redis_mod, "get_redis", lambda: fake_redis)

    # Mock embedding client
    import app.services.embedding.client as embed_mod
    mock_client = MagicMock()
    mock_client.embed_single = AsyncMock(return_value=[0.1] * 1024)
    monkeypatch.setattr(embed_mod, "get_embedding_client", lambda: mock_client)

    # 1. Create Tenant and User
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

    # Override authentication dependencies
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_tenant] = lambda: {"id": tenant.id}

    mgr = ConversationManager(db_session, tenant.id)
    conv = await mgr.create_conversation(user_id=user.id, title="Test Conversation")

    # Add 3 turns
    for idx in range(1, 4):
        await mgr.save_turn(
            conversation_id=conv.id,
            user_id=user.id,
            question=f"Q{idx}",
            answer_text=f"A{idx}",
            answer_data=None,
            sql_query=None,
            chart_hint=None,
            follow_up_questions=[],
            lineage=None,
            confidence_score=0.9,
            execution_time_ms=100,
            agents_invoked=[],
        )

    # Verify turns count is 3
    turns_res = await db_session.execute(
        select(ConversationTurn).where(ConversationTurn.conversation_id == conv.id)
    )
    assert len(turns_res.scalars().all()) == 3

    # Call delete turns endpoint to truncate from turn 2
    response = await client.delete(f"/api/v1/conversations/{conv.id}/turns/2")
    assert response.status_code == 204

    # Verify database has only turn 1
    # Expunge all cached entries to force reloading from DB
    db_session.expunge_all()
    
    turns_res = await db_session.execute(
        select(ConversationTurn).where(ConversationTurn.conversation_id == conv.id)
    )
    remaining = turns_res.scalars().all()
    assert len(remaining) == 1
    assert remaining[0].turn_number == 1
    assert remaining[0].question == "Q1"

    # Verify conv.turn_count is updated using an explicit SELECT query
    conv_res = await db_session.execute(
        select(Conversation).where(Conversation.id == conv.id)
    )
    conv_db = conv_res.scalar_one()
    assert conv_db.turn_count == 1

    # Cleanup overrides
    app.dependency_overrides.clear()
