"""Category API endpoints for CRUD operations."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.category import Category
from app.observability.db_timing import timed_execute_scalar_one, timed_execute_scalars_all
from app.observability.metrics import category_mutations_total, category_validation_failures_total
from app.observability.route import ObservabilityRoute
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate
from app.schemas.common import PaginatedResponse
from app.services.category_service import MAX_CATEGORY_DEPTH, category_depth, get_category_or_none, validate_no_cycles

router = APIRouter(route_class=ObservabilityRoute)
logger = logging.getLogger("app.categories")


class CategoryListResponse(PaginatedResponse):
    """Response model for categorylist endpoints."""
    items: list[CategoryRead]


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
async def create_category(payload: CategoryCreate, session: AsyncSession = Depends(get_session)) -> CategoryRead:
    """Create category."""
    if payload.parent_id is not None:
        parent = await get_category_or_none(session, payload.parent_id)
        if parent is None:
            category_validation_failures_total.add(1, {"reason": "parent_not_found"})
            category_mutations_total.add(1, {"operation": "create", "result": "parent_not_found"})
            logger.warning("category_create_parent_not_found", extra={"parent_id": payload.parent_id})
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent category not found")

        depth = await category_depth(session, payload.parent_id)
        if depth >= MAX_CATEGORY_DEPTH:
            category_validation_failures_total.add(1, {"reason": "depth_exceeded"})
            category_mutations_total.add(1, {"operation": "create", "result": "depth_exceeded"})
            logger.warning(
                "category_create_depth_exceeded",
                extra={"parent_id": payload.parent_id, "depth": depth, "max_depth": MAX_CATEGORY_DEPTH},
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Category depth cannot exceed {MAX_CATEGORY_DEPTH}",
            )

    category = Category(name=payload.name.strip(), parent_id=payload.parent_id)
    session.add(category)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        category_mutations_total.add(1, {"operation": "create", "result": "conflict"})
        logger.warning(
            "category_create_conflict",
            extra={"category_name": payload.name.strip(), "parent_id": payload.parent_id},
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category name must be unique per parent") from exc
    await session.refresh(category)
    category_mutations_total.add(1, {"operation": "create", "result": "success"})
    logger.info(
        "category_created",
        extra={
            "category_id": category.id,
            "category_name": category.name,
            "parent_id": category.parent_id,
        },
    )
    return CategoryRead.model_validate(category)


@router.get("/{category_id}", response_model=CategoryRead)
async def get_category(category_id: int, session: AsyncSession = Depends(get_session)) -> CategoryRead:
    """Get category."""
    category = await get_category_or_none(session, category_id)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return CategoryRead.model_validate(category)


@router.get("", response_model=CategoryListResponse)
async def list_categories(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> CategoryListResponse:
    """List categories."""
    records = await timed_execute_scalars_all(session, select(Category).limit(limit).offset(offset))
    total = await timed_execute_scalar_one(session, select(func.count()).select_from(Category))
    return CategoryListResponse(items=[CategoryRead.model_validate(item) for item in records], total=total, limit=limit, offset=offset)


@router.patch("/{category_id}", response_model=CategoryRead)
async def update_category(
    category_id: int, payload: CategoryUpdate, session: AsyncSession = Depends(get_session)
) -> CategoryRead:
    """Update category."""
    category = await get_category_or_none(session, category_id)
    if category is None:
        category_mutations_total.add(1, {"operation": "update", "result": "not_found"})
        logger.warning("category_update_not_found", extra={"category_id": category_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    updates = payload.model_dump(exclude_unset=True)

    if "parent_id" in updates:
        new_parent_id = updates["parent_id"]
        if new_parent_id is not None:
            parent = await get_category_or_none(session, new_parent_id)
            if parent is None:
                category_validation_failures_total.add(1, {"reason": "parent_not_found"})
                category_mutations_total.add(1, {"operation": "update", "result": "parent_not_found"})
                logger.warning(
                    "category_update_parent_not_found",
                    extra={"category_id": category_id, "parent_id": new_parent_id},
                )
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent category not found")

            try:
                await validate_no_cycles(session, category_id, new_parent_id)
            except ValueError as exc:
                category_validation_failures_total.add(1, {"reason": "cycle_detected"})
                category_mutations_total.add(1, {"operation": "update", "result": "cycle_detected"})
                logger.warning(
                    "category_update_cycle_detected",
                    extra={"category_id": category_id, "parent_id": new_parent_id},
                )
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

            depth = await category_depth(session, new_parent_id)
            if depth >= MAX_CATEGORY_DEPTH:
                category_validation_failures_total.add(1, {"reason": "depth_exceeded"})
                category_mutations_total.add(1, {"operation": "update", "result": "depth_exceeded"})
                logger.warning(
                    "category_update_depth_exceeded",
                    extra={
                        "category_id": category_id,
                        "parent_id": new_parent_id,
                        "depth": depth,
                        "max_depth": MAX_CATEGORY_DEPTH,
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Category depth cannot exceed {MAX_CATEGORY_DEPTH}",
                )
        category.parent_id = new_parent_id

    if "name" in updates and updates["name"] is not None:
        category.name = updates["name"].strip()

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        category_mutations_total.add(1, {"operation": "update", "result": "conflict"})
        logger.warning("category_update_conflict", extra={"category_id": category_id})
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category name must be unique per parent") from exc
    await session.refresh(category)
    category_mutations_total.add(1, {"operation": "update", "result": "success"})
    logger.info(
        "category_updated",
        extra={
            "category_id": category.id,
            "category_name": category.name,
            "parent_id": category.parent_id,
            "updated_fields": sorted(updates.keys()),
        },
    )
    return CategoryRead.model_validate(category)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(category_id: int, session: AsyncSession = Depends(get_session)) -> None:
    """Delete category."""
    category = await get_category_or_none(session, category_id)
    if category is None:
        category_mutations_total.add(1, {"operation": "delete", "result": "not_found"})
        logger.warning("category_delete_not_found", extra={"category_id": category_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    await session.delete(category)
    await session.commit()
    category_mutations_total.add(1, {"operation": "delete", "result": "success"})
    logger.info(
        "category_deleted",
        extra={"category_id": category_id, "category_name": category.name},
    )
