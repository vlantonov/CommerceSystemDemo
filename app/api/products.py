"""Product API endpoints for CRUD operations."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.product import Product
from app.observability.db_timing import timed_execute_scalar_one, timed_execute_scalars_all, timed_get
from app.observability.metrics import product_mutations_total
from app.observability.route import ObservabilityRoute
from app.schemas.common import PaginatedResponse
from app.schemas.product import ProductCreate, ProductRead, ProductUpdate

router = APIRouter(route_class=ObservabilityRoute)
logger = logging.getLogger("app.products")


def _hydrate_audit_fields(model: Product) -> Product:
    """Avoid a refresh query after commit while preserving audit timestamps.

    SQLAlchemy populates server-generated timestamps on the object during flush/commit,
    but some test stubs and mocked sessions do not. Fall back to local UTC values so the
    API response does not trigger a second SELECT just to rehydrate created_at/updated_at.
    """
    if getattr(model, "created_at", None) is None:
        model.created_at = datetime.now(timezone.utc)
    if getattr(model, "updated_at", None) is None:
        model.updated_at = datetime.now(timezone.utc)
    return model


class ProductListResponse(PaginatedResponse):
    """Response model for productlist endpoints."""
    items: list[ProductRead]


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(payload: ProductCreate, session: AsyncSession = Depends(get_session)) -> ProductRead:
    """Create product."""
    product = Product(**payload.model_dump())
    session.add(product)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        product_mutations_total.add(1, {"operation": "create", "result": "conflict"})
        logger.warning("product_create_conflict", extra={"sku": payload.sku})
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SKU must be unique") from exc

    product = _hydrate_audit_fields(product)
    product_mutations_total.add(1, {"operation": "create", "result": "success"})
    logger.info(
        "product_created",
        extra={"product_id": product.id, "sku": product.sku, "category_id": product.category_id},
    )
    return ProductRead.model_validate(product)


@router.get("/{product_id}", response_model=ProductRead)
async def get_product(product_id: int, session: AsyncSession = Depends(get_session)) -> ProductRead:
    """Get product."""
    product = await timed_get(session, Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return ProductRead.model_validate(product)


@router.get("", response_model=ProductListResponse)
async def list_products(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> ProductListResponse:
    """List products."""
    records = await timed_execute_scalars_all(session, select(Product).order_by(Product.id).limit(limit).offset(offset))
    if offset == 0 and len(records) < limit:
        total = len(records)
    else:
        total = await timed_execute_scalar_one(session, select(func.count()).select_from(Product))
    return ProductListResponse(items=[ProductRead.model_validate(item) for item in records], total=total, limit=limit, offset=offset)


@router.patch("/{product_id}", response_model=ProductRead)
async def update_product(
    product_id: int, payload: ProductUpdate, session: AsyncSession = Depends(get_session)
) -> ProductRead:
    """Update product."""
    product = await timed_get(session, Product, product_id)
    if product is None:
        product_mutations_total.add(1, {"operation": "update", "result": "not_found"})
        logger.warning("product_update_not_found", extra={"product_id": product_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(product, field, value)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        product_mutations_total.add(1, {"operation": "update", "result": "conflict"})
        logger.warning("product_update_conflict", extra={"product_id": product_id})
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SKU must be unique") from exc

    product = _hydrate_audit_fields(product)
    product_mutations_total.add(1, {"operation": "update", "result": "success"})
    logger.info(
        "product_updated",
        extra={"product_id": product.id, "sku": product.sku, "updated_fields": sorted(updates.keys())},
    )
    return ProductRead.model_validate(product)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: int, session: AsyncSession = Depends(get_session)) -> None:
    """Delete product."""
    product = await timed_get(session, Product, product_id)
    if product is None:
        product_mutations_total.add(1, {"operation": "delete", "result": "not_found"})
        logger.warning("product_delete_not_found", extra={"product_id": product_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    await session.delete(product)
    await session.commit()
    product_mutations_total.add(1, {"operation": "delete", "result": "success"})
    logger.info("product_deleted", extra={"product_id": product_id, "sku": product.sku})
