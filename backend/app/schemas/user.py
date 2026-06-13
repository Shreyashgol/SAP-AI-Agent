import uuid

from pydantic import BaseModel, EmailStr, Field


class TenantCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    slug: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    timezone: str = "UTC"


class TenantResponse(BaseModel):
    id: str
    name: str
    slug: str
    timezone: str
    is_active: bool


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8)
    role_names: list[str] = Field(default=["business_user"])


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    tenant_id: str
    is_active: bool
    roles: list[str]
    domains: list[str]


class RoleResponse(BaseModel):
    id: str
    name: str
    is_system: bool
    description: str | None


class AssignRoleRequest(BaseModel):
    user_id: uuid.UUID
    role_name: str
