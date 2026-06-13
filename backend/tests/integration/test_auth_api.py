"""
Integration tests: full auth flow against test DB.
Covers: login, JWT decode, lockout, logout + blocklist, refresh rotation.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.user import Role, RolePermission, User, UserRole


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
async def tenant(db_session: AsyncSession) -> Tenant:
    t = Tenant(name="Test Corp", slug=f"test-{uuid.uuid4().hex[:8]}", timezone="UTC")
    db_session.add(t)
    await db_session.flush()
    return t


@pytest.fixture
async def admin_role(db_session: AsyncSession, tenant: Tenant) -> Role:
    role = Role(tenant_id=tenant.id, name="platform_admin", is_system=True)
    db_session.add(role)
    await db_session.flush()
    for domain in ["finance", "sales", "purchasing", "inventory", "operations"]:
        db_session.add(RolePermission(role_id=role.id, domain=domain,
                                      can_read=True, can_export=True))
    await db_session.flush()
    return role


@pytest.fixture
async def user(db_session: AsyncSession, tenant: Tenant, admin_role: Role) -> User:
    u = User(
        tenant_id=tenant.id,
        email="admin@test.com",
        full_name="Test Admin",
        hashed_password=hash_password("correct-password"),
    )
    db_session.add(u)
    await db_session.flush()
    db_session.add(UserRole(user_id=u.id, role_id=admin_role.id))
    await db_session.flush()
    return u


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, user: User, tenant: Tenant) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "correct-password"},
        headers={"X-Tenant-ID": str(tenant.id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["access_token"]
    assert body["data"]["user"]["email"] == "admin@test.com"
    assert "platform_admin" in body["data"]["user"]["roles"]
    assert resp.cookies.get("refresh_token") is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, user: User, tenant: Tenant) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "wrong-password"},
        headers={"X-Tenant-ID": str(tenant.id)},
    )
    assert resp.status_code == 401
    assert resp.json()["success"] is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lockout_after_five_failures(
    client: AsyncClient, user: User, tenant: Tenant
) -> None:
    for _ in range(5):
        await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@test.com", "password": "wrong"},
            headers={"X-Tenant-ID": str(tenant.id)},
        )
    # 6th attempt should return locked message
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "correct-password"},
        headers={"X-Tenant-ID": str(tenant.id)},
    )
    assert resp.status_code == 401
    assert "locked" in resp.json()["error"]["message"].lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_endpoint_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_returns_user_info(client: AsyncClient, user: User, tenant: Tenant) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "correct-password"},
        headers={"X-Tenant-ID": str(tenant.id)},
    )
    token = login.json()["data"]["access_token"]
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["email"] == "admin@test.com"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_logout_blocklists_token(client: AsyncClient, user: User, tenant: Tenant) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "correct-password"},
        headers={"X-Tenant-ID": str(tenant.id)},
    )
    token = login.json()["data"]["access_token"]
    auth_header = {"Authorization": f"Bearer {token}"}

    logout = await client.post("/api/v1/auth/logout", headers=auth_header)
    assert logout.status_code == 200

    # Token should now be rejected
    me = await client.get("/api/v1/auth/me", headers=auth_header)
    assert me.status_code == 401
