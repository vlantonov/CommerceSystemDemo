"""Pydantic schemas for category payloads and responses."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CategoryBase(BaseModel):
    """Shared category fields used by create/read models."""
    name: str = Field(min_length=1, max_length=255)


class CategoryCreate(CategoryBase):
    """Payload for creating a category under an optional parent."""
    parent_id: int | None = None


class CategoryUpdate(BaseModel):
    """Partial payload for updating category name or parent link."""
    name: str | None = Field(default=None, min_length=1, max_length=255)
    parent_id: int | None = None


class CategoryRead(CategoryBase):
    """API response model for persisted category records."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    parent_id: int | None
    created_at: datetime
    updated_at: datetime
