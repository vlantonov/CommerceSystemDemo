"""Shared schema primitives such as pagination models."""

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
