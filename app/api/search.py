from decimal import Decimal
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.observability.metrics import search_requests_total, search_result_count, search_zero_results_total
from app.schemas.product import ProductRead, ProductSearchResponse
from app.services.product_service import search_products

router = APIRouter()
logger = logging.getLogger("app.search")


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
    search_attributes = {
        "has_q": str(q is not None and q.strip() != "").lower(),
        "has_category": str(category_id is not None).lower(),
        "has_price_range": str(min_price is not None or max_price is not None).lower(),
    }
    search_requests_total.add(1, search_attributes)

    if min_price is not None and max_price is not None and min_price > max_price:
        logger.warning(
            "search_invalid_price_range",
            extra={"min_price": str(min_price), "max_price": str(max_price)},
        )
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

    search_result_count.record(total, search_attributes)
    if total == 0:
        search_zero_results_total.add(1, search_attributes)

    logger.info(
        "search_completed",
        extra={
            "q_present": q is not None and q.strip() != "",
            "min_price": str(min_price) if min_price is not None else None,
            "max_price": str(max_price) if max_price is not None else None,
            "category_id": category_id,
            "limit": limit,
            "offset": offset,
            "result_count": len(products),
            "total": total,
        },
    )

    return ProductSearchResponse(
        items=[ProductRead.model_validate(item) for item in products],
        total=total,
        limit=limit,
        offset=offset,
    )
