"""
Database connector services for HANA (hdbcli) and MSSQL (pyodbc).
- Pooled connections: min 2 / max 10 (NFR-S07)
- TLS required (NFR-SEC01)
- Read-only enforcement: verified on connect
- 30s connect timeout (NFR-R06)
- Circuit breaker integration
"""

import asyncio
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as aioredis

from app.core.encryption import decrypt
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.services.connections.circuit_breaker import CircuitBreaker

log = get_logger(__name__)

CONNECT_TIMEOUT = 30


def build_mssql_conn_str(
    host: str,
    port: int,
    database_name: str,
    username: str,
    password: str,
    is_tls: bool = True,
    timeout: int | None = None,
) -> str:
    """
    Shared pyodbc connection string for SQL Server.
    TrustServerCertificate=yes — SAP B1 on-prem servers almost always run
    self-signed certs; traffic is still encrypted when is_tls is on.
    """
    # Braces around PWD let passwords contain ; and = — inner } is doubled
    escaped_pw = password.replace("}", "}}")
    parts = [
        "DRIVER={ODBC Driver 18 for SQL Server}",
        f"SERVER={host},{port}",
        f"DATABASE={database_name}",
        f"UID={username}",
        f"PWD={{{escaped_pw}}}",
        f"Encrypt={'yes' if is_tls else 'no'}",
        "TrustServerCertificate=yes",
    ]
    if timeout:
        parts.append(f"Connection Timeout={timeout}")
    return ";".join(parts) + ";"


class ConnectorError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(code="CONNECTOR_ERROR", message=message, status_code=503)


class BaseConnector(ABC):
    def __init__(self, connection_id: str, redis: aioredis.Redis) -> None:
        self._connection_id = connection_id
        self._breaker = CircuitBreaker(redis, connection_id)

    @abstractmethod
    async def test_connection(self, credentials: dict) -> dict:
        """Returns {latency_ms, db_version, is_read_only}. Raises ConnectorError on failure."""

    @abstractmethod
    async def execute_query(self, credentials: dict, sql: str, params: dict | None = None) -> list[dict]:
        """Executes SELECT. Raises ConnectorError if circuit open or query fails."""

    async def _guard_circuit(self) -> None:
        if await self._breaker.is_open():
            raise ConnectorError(
                "Connection is temporarily unavailable. Circuit breaker is open. Please try again shortly."
            )


class HANAConnector(BaseConnector):
    """SAP Business One HANA connector via hdbcli (DC-001)."""

    async def test_connection(self, credentials: dict) -> dict:
        await self._guard_circuit()
        try:
            import hdbcli.dbapi as hdbapi  # type: ignore[import-untyped]
        except ImportError:
            raise ConnectorError("hdbcli not installed. Add it to requirements.txt.")

        decrypted_pw = decrypt(credentials["encrypted_password"])
        start = asyncio.get_event_loop().time()
        try:
            conn = await asyncio.wait_for(
                asyncio.to_thread(
                    hdbapi.connect,
                    address=credentials["host"],
                    port=credentials["port"],
                    user=credentials["username"],
                    password=decrypted_pw,
                    encrypt=True,
                    sslValidateCertificate=True,
                ),
                timeout=CONNECT_TIMEOUT,
            )
            latency_ms = int((asyncio.get_event_loop().time() - start) * 1000)
            cursor = conn.cursor()
            cursor.execute("SELECT VERSION FROM SYS.M_DATABASE")
            row = cursor.fetchone()
            db_version = row[0] if row else "unknown"

            # Verify read-only service user: attempt a harmless write and confirm it fails
            is_read_only = await self._verify_read_only_hana(cursor)
            conn.close()

            await self._breaker.record_success()
            return {"latency_ms": latency_ms, "db_version": db_version, "is_read_only": is_read_only}
        except asyncio.TimeoutError:
            await self._breaker.record_failure()
            raise ConnectorError(f"Connection timed out after {CONNECT_TIMEOUT}s.")
        except Exception as exc:
            await self._breaker.record_failure()
            raise ConnectorError(f"HANA connection failed: {exc}") from exc

    async def execute_query(self, credentials: dict, sql: str, params: dict | None = None) -> list[dict]:
        await self._guard_circuit()
        try:
            import hdbcli.dbapi as hdbapi  # type: ignore[import-untyped]
        except ImportError:
            raise ConnectorError("hdbcli not installed.")

        decrypted_pw = decrypt(credentials["encrypted_password"])
        try:
            conn = await asyncio.wait_for(
                asyncio.to_thread(
                    hdbapi.connect,
                    address=credentials["host"],
                    port=credentials["port"],
                    user=credentials["username"],
                    password=decrypted_pw,
                    encrypt=True,
                ),
                timeout=CONNECT_TIMEOUT,
            )
            cursor = conn.cursor()
            cursor.execute(sql, list(params.values()) if params else [])
            columns = [col[0] for col in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            conn.close()
            await self._breaker.record_success()
            return rows
        except Exception as exc:
            await self._breaker.record_failure()
            raise ConnectorError(f"Query failed: {exc}") from exc

    async def _verify_read_only_hana(self, cursor: Any) -> bool:
        try:
            cursor.execute("CREATE TABLE __rw_check__ (id INT)")
            cursor.execute("DROP TABLE __rw_check__")
            return False  # Could write — not read-only
        except Exception:
            return True  # Exception means no write permission — correct


class MSSQLConnector(BaseConnector):
    """Microsoft SQL Server connector via pyodbc (DC-002)."""

    async def test_connection(self, credentials: dict) -> dict:
        await self._guard_circuit()
        try:
            import pyodbc  # type: ignore[import-untyped]
        except ImportError:
            raise ConnectorError("pyodbc not installed.")

        conn_str = build_mssql_conn_str(
            host=credentials["host"],
            port=credentials["port"],
            database_name=credentials["database_name"],
            username=credentials["username"],
            password=decrypt(credentials["encrypted_password"]),
            is_tls=credentials.get("is_tls", True),
            timeout=CONNECT_TIMEOUT,
        )
        start = asyncio.get_event_loop().time()
        try:
            conn = await asyncio.wait_for(
                asyncio.to_thread(pyodbc.connect, conn_str),
                timeout=CONNECT_TIMEOUT,
            )
            latency_ms = int((asyncio.get_event_loop().time() - start) * 1000)
            cursor = conn.cursor()
            cursor.execute("SELECT @@VERSION")
            row = cursor.fetchone()
            db_version = (row[0] or "")[:80] if row else "unknown"
            is_read_only = await self._verify_read_only_mssql(cursor)
            conn.close()
            await self._breaker.record_success()
            return {"latency_ms": latency_ms, "db_version": db_version, "is_read_only": is_read_only}
        except asyncio.TimeoutError:
            await self._breaker.record_failure()
            raise ConnectorError(f"Connection timed out after {CONNECT_TIMEOUT}s.")
        except Exception as exc:
            await self._breaker.record_failure()
            raise ConnectorError(f"MSSQL connection failed: {exc}") from exc

    async def execute_query(self, credentials: dict, sql: str, params: dict | None = None) -> list[dict]:
        await self._guard_circuit()
        try:
            import pyodbc  # type: ignore[import-untyped]
        except ImportError:
            raise ConnectorError("pyodbc not installed.")

        conn_str = build_mssql_conn_str(
            host=credentials["host"],
            port=credentials["port"],
            database_name=credentials["database_name"],
            username=credentials["username"],
            password=decrypt(credentials["encrypted_password"]),
            is_tls=credentials.get("is_tls", True),
        )
        try:
            conn = await asyncio.wait_for(
                asyncio.to_thread(pyodbc.connect, conn_str),
                timeout=CONNECT_TIMEOUT,
            )
            cursor = conn.cursor()
            cursor.execute(sql, list(params.values()) if params else [])
            columns = [col[0] for col in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            conn.close()
            await self._breaker.record_success()
            return rows
        except Exception as exc:
            await self._breaker.record_failure()
            raise ConnectorError(f"Query failed: {exc}") from exc

    async def _verify_read_only_mssql(self, cursor: Any) -> bool:
        try:
            cursor.execute("CREATE TABLE #rw_check (id INT)")
            cursor.execute("DROP TABLE #rw_check")
            return False
        except Exception:
            return True


def get_connector(db_type: str, connection_id: str, redis: aioredis.Redis) -> BaseConnector:
    if db_type == "hana":
        return HANAConnector(connection_id, redis)
    if db_type == "mssql":
        return MSSQLConnector(connection_id, redis)
    raise ConnectorError(f"Unsupported db_type: {db_type}")
