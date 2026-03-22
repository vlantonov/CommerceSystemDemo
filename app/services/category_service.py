"""Category business logic helpers and hierarchy utilities."""

from sqlalchemy import Select, exists, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.observability.db_timing import timed_execute_scalar_one, timed_get

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


def _ancestor_chain_cte(start_category_id: int, depth_limit: int | None = None):
    """Build a recursive CTE that walks from a category to the root by parent links."""
    ancestor_chain: Select = (
        select(
            Category.id.label("id"),
            Category.parent_id.label("parent_id"),
            literal(1).label("depth"),
        )
        .where(Category.id == start_category_id)
        .cte(name="ancestor_chain", recursive=True)
    )

    category_alias = Category.__table__.alias("category_alias")
    recursive_step = select(
        category_alias.c.id,
        category_alias.c.parent_id,
        (ancestor_chain.c.depth + 1).label("depth"),
    ).where(category_alias.c.id == ancestor_chain.c.parent_id)

    if depth_limit is not None:
        recursive_step = recursive_step.where(ancestor_chain.c.depth < depth_limit)

    return ancestor_chain.union_all(recursive_step)


async def category_depth(session: AsyncSession, parent_id: int | None) -> int:
    """Compute ancestor depth for a parent candidate in the category tree."""
    if parent_id is None:
        return 0

    ancestor_chain = _ancestor_chain_cte(parent_id, depth_limit=MAX_CATEGORY_DEPTH + 1)
    depth_statement = select(func.coalesce(func.max(ancestor_chain.c.depth), 0))
    depth = await timed_execute_scalar_one(session, depth_statement)
    return int(depth)


async def validate_no_cycles(session: AsyncSession, category_id: int, new_parent_id: int | None) -> None:
    """Ensure re-parenting a category does not create a cycle."""
    if new_parent_id is None:
        return

    ancestor_chain = _ancestor_chain_cte(new_parent_id, depth_limit=MAX_CATEGORY_DEPTH + 1)
    cycle_check_statement = select(
        exists(
            select(1)
            .select_from(ancestor_chain)
            .where(ancestor_chain.c.id == category_id)
        )
    )
    cycle_detected = await timed_execute_scalar_one(session, cycle_check_statement)
    if bool(cycle_detected):
        raise ValueError("Category cycle detected")


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
