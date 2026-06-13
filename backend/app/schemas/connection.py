from typing import Literal

from pydantic import BaseModel, Field


class ConnectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    db_type: Literal["hana", "mssql"]
    host: str = Field(..., min_length=1, max_length=500)
    port: int = Field(..., gt=0, lt=65536)
    database_name: str = Field(..., min_length=1, max_length=255)
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    is_tls: bool = True


class ConnectionUpdate(BaseModel):
    name: str | None = None
    username: str | None = None
    password: str | None = None


class ConnectionResponse(BaseModel):
    id: str
    name: str
    db_type: str
    host: str
    port: int
    database_name: str
    is_active: bool
    is_tls: bool
    last_health_status: str | None
    last_health_check_at: str | None


class ConnectionTestResult(BaseModel):
    success: bool
    latency_ms: int | None = None
    db_version: str | None = None
    is_read_only: bool | None = None
    error: str | None = None
