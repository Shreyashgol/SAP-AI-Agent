import math
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, model_validator

DataT = TypeVar("DataT")


class APIResponse(BaseModel, Generic[DataT]):
    """Standard response envelope for all API endpoints."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool = True
    data: DataT | None = None
    message: str | None = None
    request_id: str | None = None


class PaginatedResponse(BaseModel, Generic[DataT]):
    """Paginated list response envelope."""

    success: bool = True
    data: list[DataT]
    total: int
    page: int
    page_size: int
    pages: int = 0
    request_id: str | None = None

    @model_validator(mode="after")
    def _compute_pages(self) -> "PaginatedResponse[DataT]":
        if self.pages == 0 and self.page_size > 0:
            self.pages = math.ceil(self.total / self.page_size) if self.total > 0 else 1
        return self


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: str | None = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail
    request_id: str | None = None
