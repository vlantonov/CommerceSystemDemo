"""Shared schema primitives such as pagination models."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PaginationQuery(BaseModel):
    """Schema for paginationquery."""
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class PaginatedResponse(BaseModel):
    """Schema for paginatedresponse."""
    model_config = ConfigDict(from_attributes=True)

    total: int
    limit: int
    offset: int


class ErrorDetailResponse(BaseModel):
    """Schema for HTTP exception responses."""

    detail: str


class FlexibleValidationErrorResponse(BaseModel):
    """Schema for validation-style responses with string or list detail."""

    detail: str | list[dict[str, Any]]


class RateLimitErrorResponse(BaseModel):
    """Schema for rate-limit responses from SlowAPI."""

    error: str
