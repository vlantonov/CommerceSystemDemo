"""Pydantic schemas for product payloads and search responses."""

from datetime import datetime
from decimal import Decimal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_serializer, field_validator


SKU_REGEX = r"^[A-Z0-9_-]{1,100}$"


class ProductBase(BaseModel):
    """Schema for productbase."""
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=10000)
    image_url: AnyHttpUrl | None = Field(default=None)
    sku: str = Field(min_length=1, max_length=100, pattern=SKU_REGEX)
    price: Decimal = Field(ge=Decimal("0"))
    category_id: int | None = None

    @field_serializer("image_url")
    def serialize_image_url(self, value: AnyHttpUrl | None) -> str | None:
        return str(value) if value is not None else None

    @field_validator("title", mode="before")
    @classmethod
    def validate_title(cls, value: str) -> str:
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                raise ValueError("Title cannot be empty or contain only whitespace")
        return value

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, value: str) -> str:
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                raise ValueError("Description cannot be empty or contain only whitespace")
        return value

    @field_validator("sku", mode="before")
    @classmethod
    def normalize_sku(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        return value.upper()


class ProductCreate(ProductBase):
    """Schema for productcreate."""
    pass


class ProductUpdate(BaseModel):
    """Schema for productupdate."""
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=10000)
    image_url: AnyHttpUrl | None = Field(default=None)
    sku: str | None = Field(default=None, min_length=1, max_length=100, pattern=SKU_REGEX)
    price: Decimal | None = Field(default=None, ge=Decimal("0"))
    category_id: int | None = None

    @field_validator("title", mode="before")
    @classmethod
    def validate_optional_title(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                raise ValueError("Title cannot be empty or contain only whitespace")
        return value

    @field_validator("description", mode="before")
    @classmethod
    def validate_optional_description(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                raise ValueError("Description cannot be empty or contain only whitespace")
        return value

    @field_validator("sku", mode="before")
    @classmethod
    def normalize_optional_sku(cls, value: str | None) -> str | None:
        if value is None or not isinstance(value, str):
            return value
        return value.upper()


class ProductRead(ProductBase):
    """Schema for productread."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class ProductSearchResponse(BaseModel):
    """Schema for productsearchresponse."""
    items: list[ProductRead]
    total: int
    limit: int
    offset: int
