"""
MSSQL connection path unit tests.

Covers:
  - build_mssql_conn_str: TLS flag, timeout, password escaping (DC-002)
  - Credential blob round-trip: special characters survive encrypt/store/load
  - Legacy blobs without is_tls fall back to the connection row's flag
"""

from types import SimpleNamespace

import pytest

from app.core.encryption import decrypt
from app.schemas.connection import ConnectionCreate
from app.services.connections.connection_service import ConnectionService
from app.services.connections.connector import build_mssql_conn_str


def _parse_conn_str(conn_str: str) -> dict:
    """Split 'K=V;K=V;' into a dict (values may contain '=' so split once)."""
    pairs = [p for p in conn_str.split(";") if p]
    return dict(p.split("=", 1) for p in pairs)


# ── build_mssql_conn_str ──────────────────────────────────────────────────────

@pytest.mark.unit
def test_conn_str_tls_on() -> None:
    conn_str = build_mssql_conn_str(
        host="192.168.162.4",
        port=30013,
        database_name="MEGATRADE_LIVE",
        username="sa",
        password="pw",
        is_tls=True,
    )
    parts = _parse_conn_str(conn_str)
    assert parts["DRIVER"] == "{ODBC Driver 18 for SQL Server}"
    assert parts["SERVER"] == "192.168.162.4,30013"
    assert parts["DATABASE"] == "MEGATRADE_LIVE"
    assert parts["UID"] == "sa"
    assert parts["Encrypt"] == "yes"
    # Self-signed certs are the norm on SAP B1 on-prem servers
    assert parts["TrustServerCertificate"] == "yes"


@pytest.mark.unit
def test_conn_str_tls_off() -> None:
    conn_str = build_mssql_conn_str(
        host="h", port=1433, database_name="db", username="u",
        password="pw", is_tls=False,
    )
    assert _parse_conn_str(conn_str)["Encrypt"] == "no"


@pytest.mark.unit
def test_conn_str_timeout_only_when_requested() -> None:
    with_timeout = build_mssql_conn_str(
        host="h", port=1433, database_name="db", username="u",
        password="pw", timeout=30,
    )
    without_timeout = build_mssql_conn_str(
        host="h", port=1433, database_name="db", username="u", password="pw",
    )
    assert _parse_conn_str(with_timeout)["Connection Timeout"] == "30"
    assert "Connection Timeout" not in without_timeout


@pytest.mark.unit
def test_conn_str_password_is_brace_escaped() -> None:
    """Passwords with ; = } must not break the ODBC connection string."""
    conn_str = build_mssql_conn_str(
        host="h", port=1433, database_name="db", username="u",
        password="Tech;ative=1}23",
    )
    assert "PWD={Tech;ative=1}}23}" in conn_str
    # The literal password must never appear unescaped/unbraced
    assert "PWD=Tech" not in conn_str


# ── Credential blob round-trip ────────────────────────────────────────────────

def _load(blob: str, is_tls_on_row: bool = True) -> dict:
    svc = ConnectionService(db=None, redis=None)  # type: ignore[arg-type]
    stub_conn = SimpleNamespace(
        vault_credential_path=f"local:{blob}", is_tls=is_tls_on_row
    )
    return svc._load_credentials(stub_conn)  # type: ignore[arg-type]


@pytest.mark.unit
def test_credential_blob_round_trip_with_special_chars() -> None:
    """Quotes/backslashes in passwords must survive store → load (old f-string bug)."""
    body = ConnectionCreate(
        name="SAP B1 Production",
        db_type="mssql",
        host="192.168.162.4",
        port=30013,
        database_name="MEGATRADE_LIVE",
        username="sa",
        password='we!rd"pass\\word{};=',
        is_tls=True,
    )
    creds = _load(ConnectionService._build_credential_blob(body))

    assert creds["username"] == "sa"
    assert creds["host"] == "192.168.162.4"
    assert creds["port"] == 30013
    assert creds["database_name"] == "MEGATRADE_LIVE"
    assert creds["is_tls"] is True
    # Password is double-encrypted: blob layer + per-field layer
    assert decrypt(creds["encrypted_password"]) == 'we!rd"pass\\word{};='


@pytest.mark.unit
def test_legacy_blob_without_is_tls_falls_back_to_row() -> None:
    """Blobs written before is_tls was stored use the connection row's flag."""
    import json

    from app.core.encryption import encrypt

    legacy_blob = encrypt(json.dumps({
        "username": "sa",
        "encrypted_password": encrypt("pw"),
        "host": "h",
        "port": 1433,
        "database_name": "db",
    }))
    assert _load(legacy_blob, is_tls_on_row=False)["is_tls"] is False
    assert _load(legacy_blob, is_tls_on_row=True)["is_tls"] is True
