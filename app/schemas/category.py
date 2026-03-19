"""Pydantic schemas for category payloads and responses."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CategoryBase(BaseModel):
    """Shared category fields used by create/read models."""
    name: str = Field(min_length=1, max_length=255)

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                raise ValueError("Category name cannot be empty or contain only whitespace")
        return value


class CategoryCreate(CategoryBase):
    """Payload for creating a category under an optional parent."""
    parent_id: int | None = None


class CategoryUpdate(BaseModel):
    """Partial payload for updating category name or parent link."""
    name: str | None = Field(default=None, min_length=1, max_length=255)
    parent_id: int | None = None

    @field_validator("name", mode="before")
    @classmethod
    def validate_optional_name(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                raise ValueError("Category name cannot be empty or contain only whitespace")
        return value


class CategoryRead(CategoryBase):
    """API response model for persisted category records."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    parent_id: int | None
    created_at: datetime
    updated_at: datetime
