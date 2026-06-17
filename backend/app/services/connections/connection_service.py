"""
Connection CRUD + health check service.
Credentials are AES-256 encrypted before storage.
The encrypted blob is stored as vault_credential_path (acting as our dev Vault).
Raw passwords are NEVER returned via any API response (DC-012).
"""

import json
import uuid
from datetime import UTC, datetime

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt, encrypt
from app.core.exceptions import ConflictError, NotFoundError
from app.models.connection import Connection
from app.schemas.connection import ConnectionCreate, ConnectionTestResult
from app.services.connections.connector import ConnectorError, get_connector, normalize_db_host


class ConnectionService:
    def __init__(self, db: AsyncSession, redis: aioredis.Redis) -> None:
        self.db = db
        self.redis = redis

    async def create(self, tenant_id: uuid.UUID, body: ConnectionCreate) -> Connection:
        # Uniqueness check
        existing = await self.db.execute(
            select(Connection).where(
                Connection.tenant_id == tenant_id,
                Connection.name == body.name,
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"Connection '{body.name}' already exists.")

        # A loopback host can't reach a DB published on the host machine when the
        # API runs in a container — rewrite it once so both the stored column and
        # the credential blob (which the connector actually dials) stay in sync.
        body.host = normalize_db_host(body.host)

        # Encrypt credentials — store as JSON blob, path = "local:{blob}"
        cred_blob = self._build_credential_blob(body)

        conn = Connection(
            tenant_id=tenant_id,
            name=body.name,
            db_type=body.db_type,
            host=body.host,
            port=body.port,
            database_name=body.database_name,
            vault_credential_path=f"local:{cred_blob}",
            is_tls=body.is_tls,
        )
        self.db.add(conn)
        await self.db.commit()
        await self.db.refresh(conn)
        return conn

    async def test(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> ConnectionTestResult:
        conn = await self._get(tenant_id, connection_id)
        credentials = self._load_credentials(conn)
        connector = get_connector(conn.db_type, str(connection_id), self.redis)
        try:
            result = await connector.test_connection(credentials)
            conn.last_health_status = "ok"
            conn.last_health_check_at = datetime.now(UTC).isoformat()
            await self.db.commit()
            return ConnectionTestResult(success=True, **result)
        except ConnectorError as exc:
            conn.last_health_status = "error"
            conn.last_health_check_at = datetime.now(UTC).isoformat()
            await self.db.commit()
            return ConnectionTestResult(success=False, error=exc.message)

    async def list_connections(self, tenant_id: uuid.UUID) -> list[Connection]:
        result = await self.db.execute(
            select(Connection).where(
                Connection.tenant_id == tenant_id,
                Connection.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    async def get(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> Connection:
        return await self._get(tenant_id, connection_id)

    async def delete(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> None:
        conn = await self._get(tenant_id, connection_id)
        conn.is_active = False
        await self.db.commit()

    # ── Credential access (internal only) ─────────────────────────────────────
    @staticmethod
    def _build_credential_blob(body: ConnectionCreate) -> str:
        return encrypt(
            json.dumps(
                {
                    "username": body.username,
                    "encrypted_password": encrypt(body.password),
                    "host": body.host,
                    "port": body.port,
                    "database_name": body.database_name,
                    "is_tls": body.is_tls,
                }
            )
        )

    def _load_credentials(self, conn: Connection) -> dict:
        blob = conn.vault_credential_path.removeprefix("local:")
        credentials = json.loads(decrypt(blob))
        # Blobs written before is_tls was stored default to TLS on
        credentials.setdefault("is_tls", conn.is_tls)
        # Self-correct the host for the current runtime (container vs bare metal)
        # so blobs saved with a now-unreachable host (e.g. host.docker.internal
        # written under Docker, then run via run_local.sh) still connect.
        credentials["host"] = normalize_db_host(credentials.get("host", conn.host))
        return credentials

    async def _get(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> Connection:
        result = await self.db.execute(
            select(Connection).where(
                Connection.id == connection_id,
                Connection.tenant_id == tenant_id,
                Connection.is_active.is_(True),
            )
        )
        conn = result.scalar_one_or_none()
        if not conn:
            raise NotFoundError("Connection")
        return conn
