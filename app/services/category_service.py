"""Category business logic helpers and hierarchy utilities."""

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.observability.db_timing import timed_get

MAX_CATEGORY_DEPTH = 100


class CategoryParentNotFoundError(LookupError):
    """Raised when a referenced parent category does not exist."""


class CategoryDepthError(ValueError):
    """Raised when attaching to a parent would exceed the maximum depth."""


class CategoryCycleError(ValueError):
    """Raised when re-parenting a category would create a cycle."""


async def get_category_or_none(session: AsyncSession, category_id: int) -> Category | None:
    """Return a category by id, or `None` if it does not exist."""
    return await timed_get(session, Category, category_id)


async def category_depth(session: AsyncSession, parent_id: int | None) -> int:
    """Compute ancestor depth for a parent candidate in the category tree."""
    depth = 0
    current_parent_id = parent_id
    while current_parent_id is not None:
        depth += 1
        if depth > MAX_CATEGORY_DEPTH:
            return depth
        parent = await timed_get(session, Category, current_parent_id)
        if parent is None:
            break
        current_parent_id = parent.parent_id
    return depth


async def validate_no_cycles(session: AsyncSession, category_id: int, new_parent_id: int | None) -> None:
    """Ensure re-parenting a category does not create a cycle."""
    cursor = new_parent_id
    while cursor is not None:
        if cursor == category_id:
            raise ValueError("Category cycle detected")
        candidate = await timed_get(session, Category, cursor)
        if candidate is None:
            break
        cursor = candidate.parent_id


def category_subtree_cte(root_category_id: int):
    """Build a recursive CTE for a category and all of its descendants."""
    category_tree: Select = select(Category.id).where(Category.id == root_category_id).cte(
        name="category_tree", recursive=True
    )
    category_alias = Category.__table__.alias("category_alias")
    category_tree = category_tree.union_all(
        select(category_alias.c.id).where(category_alias.c.parent_id == category_tree.c.id)
    )
    return category_tree


async def validate_category_parent(session: AsyncSession, parent_id: int) -> None:
    """Validate that a parent category exists and is within depth limits.

    Raises:
        CategoryParentNotFoundError: if the parent does not exist.
        CategoryDepthError: if attaching here would exceed MAX_CATEGORY_DEPTH.
    """
    parent = await get_category_or_none(session, parent_id)
    if parent is None:
        raise CategoryParentNotFoundError(parent_id)
    depth = await category_depth(session, parent_id)
    if depth >= MAX_CATEGORY_DEPTH:
        raise CategoryDepthError(MAX_CATEGORY_DEPTH)


async def validate_category_reparent(
    session: AsyncSession, category_id: int, new_parent_id: int | None
) -> None:
    """Validate re-parenting a category: parent exists, no cycles, depth within limits.

    Raises:
        CategoryParentNotFoundError: if the new parent does not exist.
        CategoryCycleError: if the re-parent creates a cycle.
        CategoryDepthError: if the re-parent would exceed MAX_CATEGORY_DEPTH.
    """
    if new_parent_id is None:
        return
    parent = await get_category_or_none(session, new_parent_id)
    if parent is None:
        raise CategoryParentNotFoundError(new_parent_id)
    try:
        await validate_no_cycles(session, category_id, new_parent_id)
    except ValueError as exc:
        raise CategoryCycleError(str(exc)) from exc
    depth = await category_depth(session, new_parent_id)
    if depth >= MAX_CATEGORY_DEPTH:
        raise CategoryDepthError(MAX_CATEGORY_DEPTH)
