from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


SKU_REGEX = r"^[A-Z0-9_-]{1,100}$"


class ProductBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=10000)
    image_url: str | None = Field(default=None, max_length=2083)
    sku: str = Field(min_length=1, max_length=100, pattern=SKU_REGEX)
    price: Decimal = Field(ge=Decimal("0"))
    category_id: int | None = None

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: str) -> str:
        return value.upper()


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=10000)
    image_url: str | None = Field(default=None, max_length=2083)
    sku: str | None = Field(default=None, min_length=1, max_length=100, pattern=SKU_REGEX)
    price: Decimal | None = Field(default=None, ge=Decimal("0"))
    category_id: int | None = None

    @field_validator("sku")
    @classmethod
    def normalize_optional_sku(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.upper()


class ProductRead(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class ProductSearchResponse(BaseModel):
    items: list[ProductRead]
    total: int
    limit: int
    offset: int
