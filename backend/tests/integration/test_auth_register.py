"""
Integration tests: self-serve signup + email-based sign-in.
Covers: POST /auth/register creates a new org + admin and signs in; login then
works with NO X-Tenant-ID header (tenant resolved from the email); duplicate
email is rejected.
"""

import uuid

import pytest
from httpx import AsyncClient


def _unique_email() -> str:
    return f"founder-{uuid.uuid4().hex[:8]}@newco.com"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_creates_org_and_signs_in(client: AsyncClient) -> None:
    email = _unique_email()
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "New Co",
            "full_name": "Casey Founder",
            "email": email,
            "password": "supersecret1",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["access_token"]
    assert body["data"]["user"]["email"] == email
    assert "platform_admin" in body["data"]["user"]["roles"]
    assert resp.cookies.get("refresh_token") is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_login_by_email_without_tenant_header(client: AsyncClient) -> None:
    email = _unique_email()
    await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Resolve Co",
            "full_name": "Pat Owner",
            "email": email,
            "password": "supersecret1",
        },
    )
    # No X-Tenant-ID header — the backend must resolve the org from the email.
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "supersecret1"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["user"]["email"] == email


@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_duplicate_email_conflicts(client: AsyncClient) -> None:
    email = _unique_email()
    payload = {
        "organization_name": "Dup Co",
        "full_name": "First Person",
        "email": email,
        "password": "supersecret1",
    }
    first = await client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/auth/register",
        json={**payload, "organization_name": "Dup Co Two"},
    )
    assert second.status_code == 409, second.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_forgot_then_reset_password(client: AsyncClient) -> None:
    email = _unique_email()
    await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Reset Co",
            "full_name": "Reed Set",
            "email": email,
            "password": "originalpw1",
        },
    )
    # Request reset — non-production returns the token in the response.
    forgot = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert forgot.status_code == 200
    token = forgot.json()["data"]["reset_token"]
    assert token

    reset = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "brandnewpw9"},
    )
    assert reset.status_code == 200, reset.text

    # New password works; old one no longer does.
    ok = await client.post("/api/v1/auth/login", json={"email": email, "password": "brandnewpw9"})
    assert ok.status_code == 200
    bad = await client.post("/api/v1/auth/login", json={"email": email, "password": "originalpw1"})
    assert bad.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_forgot_password_unknown_email_is_ok(client: AsyncClient) -> None:
    # Never reveals whether the email exists — always 200, no token.
    resp = await client.post("/api/v1/auth/forgot-password", json={"email": _unique_email()})
    assert resp.status_code == 200
    assert resp.json()["data"]["reset_token"] is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reset_password_bad_token(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": "totally-invalid-token", "new_password": "whatever12"},
    )
    assert resp.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_rejects_short_password(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Short Pw Co",
            "full_name": "Tiny Pass",
            "email": _unique_email(),
            "password": "short",
        },
    )
    assert resp.status_code == 422  # pydantic min_length=8
