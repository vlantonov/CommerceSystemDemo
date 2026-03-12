from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.product import ProductRead, ProductSearchResponse
from app.services.product_service import search_products

router = APIRouter()


@router.get("/search", response_model=ProductSearchResponse)
async def search_products_endpoint(
    q: str | None = Query(default=None, min_length=1, max_length=255),
    min_price: Decimal | None = Query(default=None, ge=Decimal("0")),
    max_price: Decimal | None = Query(default=None, ge=Decimal("0")),
    category_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> ProductSearchResponse:
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(status_code=422, detail="min_price cannot be greater than max_price")

    products, total = await search_products(
        session,
        q=q,
        min_price=min_price,
        max_price=max_price,
        category_id=category_id,
        limit=limit,
        offset=offset,
    )
    return ProductSearchResponse(
        items=[ProductRead.model_validate(item) for item in products],
        total=total,
        limit=limit,
        offset=offset,
    )
