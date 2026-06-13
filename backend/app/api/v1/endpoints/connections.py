"""
Connections API — CRUD + test + health (DC-001–003, DC-012).
Credentials are NEVER returned in any response after save.
"""

import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, RequirePlatformAdmin, get_redis
from app.db.session import get_db
from app.schemas.base import APIResponse
from app.schemas.connection import (
    ConnectionCreate,
    ConnectionResponse,
    ConnectionTestResult,
)
from app.services.connections.connection_service import ConnectionService

router = APIRouter(prefix="/connections", tags=["connections"])


def _svc(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> ConnectionService:
    return ConnectionService(db, redis)


def _to_response(conn) -> ConnectionResponse:
    return ConnectionResponse(
        id=str(conn.id),
        name=conn.name,
        db_type=conn.db_type,
        host=conn.host,
        port=conn.port,
        database_name=conn.database_name,
        is_active=conn.is_active,
        is_tls=conn.is_tls,
        last_health_status=conn.last_health_status,
        last_health_check_at=conn.last_health_check_at,
    )


@router.post("", response_model=APIResponse[ConnectionResponse], status_code=201,
             dependencies=[RequirePlatformAdmin])
async def create_connection(
    body: ConnectionCreate,
    current_user: CurrentUser,
    svc: ConnectionService = Depends(_svc),
) -> APIResponse[ConnectionResponse]:
    conn = await svc.create(current_user.tenant_id, body)
    return APIResponse(data=_to_response(conn), message="Connection created.")


@router.get("", response_model=APIResponse[list[ConnectionResponse]])
async def list_connections(
    current_user: CurrentUser,
    svc: ConnectionService = Depends(_svc),
) -> APIResponse[list[ConnectionResponse]]:
    conns = await svc.list_connections(current_user.tenant_id)
    return APIResponse(data=[_to_response(c) for c in conns])


@router.get("/{connection_id}", response_model=APIResponse[ConnectionResponse])
async def get_connection(
    connection_id: uuid.UUID,
    current_user: CurrentUser,
    svc: ConnectionService = Depends(_svc),
) -> APIResponse[ConnectionResponse]:
    conn = await svc.get(current_user.tenant_id, connection_id)
    return APIResponse(data=_to_response(conn))


@router.post("/{connection_id}/test", response_model=APIResponse[ConnectionTestResult])
async def test_connection(
    connection_id: uuid.UUID,
    current_user: CurrentUser,
    svc: ConnectionService = Depends(_svc),
) -> APIResponse[ConnectionTestResult]:
    result = await svc.test(current_user.tenant_id, connection_id)
    return APIResponse(data=result)


@router.delete("/{connection_id}", response_model=APIResponse[None],
               dependencies=[RequirePlatformAdmin])
async def delete_connection(
    connection_id: uuid.UUID,
    current_user: CurrentUser,
    svc: ConnectionService = Depends(_svc),
) -> APIResponse[None]:
    await svc.delete(current_user.tenant_id, connection_id)
    return APIResponse(message="Connection removed.")
