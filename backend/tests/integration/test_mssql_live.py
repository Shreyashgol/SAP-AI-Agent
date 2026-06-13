"""
Live MSSQL connectivity test — runs only when MSSQL_TEST_* env vars are set,
so CI and local runs without a reachable SQL Server skip it automatically.

Must be run from a machine that can reach the SQL Server (same LAN / VPN).

Usage:
    export MSSQL_TEST_HOST=192.168.162.4
    export MSSQL_TEST_PORT=30013
    export MSSQL_TEST_DB=MEGATRADE_LIVE
    export MSSQL_TEST_USER=sa
    export MSSQL_TEST_PASSWORD='<password>'
    pytest tests/integration/test_mssql_live.py -m integration --no-cov -rs
"""

import os

import pytest

from app.services.connections.connector import build_mssql_conn_str

REQUIRED_VARS = (
    "MSSQL_TEST_HOST",
    "MSSQL_TEST_PORT",
    "MSSQL_TEST_DB",
    "MSSQL_TEST_USER",
    "MSSQL_TEST_PASSWORD",
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not all(os.environ.get(v) for v in REQUIRED_VARS),
        reason=f"Set {', '.join(REQUIRED_VARS)} to run the live MSSQL test",
    ),
]


@pytest.fixture(scope="module")
def conn_str() -> str:
    return build_mssql_conn_str(
        host=os.environ["MSSQL_TEST_HOST"],
        port=int(os.environ["MSSQL_TEST_PORT"]),
        database_name=os.environ["MSSQL_TEST_DB"],
        username=os.environ["MSSQL_TEST_USER"],
        password=os.environ["MSSQL_TEST_PASSWORD"],
        is_tls=os.environ.get("MSSQL_TEST_TLS", "1") not in ("0", "false", "no"),
        timeout=30,
    )


def test_can_connect_and_query(conn_str: str) -> None:
    pyodbc = pytest.importorskip("pyodbc", reason="pyodbc not installed")

    conn = pyodbc.connect(conn_str)
    try:
        cursor = conn.cursor()

        cursor.execute("SELECT @@VERSION")
        version = cursor.fetchone()[0]
        assert "SQL Server" in version

        cursor.execute("SELECT DB_NAME()")
        assert cursor.fetchone()[0] == os.environ["MSSQL_TEST_DB"]

        # The discovery crawler needs catalog access — verify it sees tables
        cursor.execute("SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES")
        assert cursor.fetchone()[0] > 0
    finally:
        conn.close()


def test_sap_b1_core_tables_visible(conn_str: str) -> None:
    """SAP B1 databases expose OCRD (customers) / OINV (invoices) etc."""
    pyodbc = pytest.importorskip("pyodbc", reason="pyodbc not installed")

    conn = pyodbc.connect(conn_str)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_NAME IN ('OCRD', 'OINV', 'ORDR', 'OITM')"
        )
        found = cursor.fetchone()[0]
        if found == 0:
            pytest.skip("No SAP B1 core tables found — not a B1 database?")
        assert found > 0
    finally:
        conn.close()
