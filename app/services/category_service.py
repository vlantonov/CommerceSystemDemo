"""Category business logic helpers and hierarchy utilities."""

import json
import logging

from redis.exceptions import RedisError
from sqlalchemy import Select, exists, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.redis_client import get_redis_client
from app.core.config import get_settings
from app.models.category import Category
from app.observability.db_timing import (
    timed_execute_one,
    timed_execute_scalar_one,
    timed_execute_scalars_all,
    timed_get,
)

MAX_CATEGORY_DEPTH = 100
_CATEGORY_SUBTREE_VERSION_KEY = "category_subtree_cache_version"

logger = logging.getLogger("app.categories")


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


async def _query_category_subtree_ids(session: AsyncSession, category_id: int) -> list[int]:
    """Return root + descendant ids from PostgreSQL via recursive CTE."""
    category_tree = category_subtree_cte(category_id)
    statement = select(category_tree.c.id).order_by(category_tree.c.id)
    rows = await timed_execute_scalars_all(session, statement)
    return [int(category_tree_id) for category_tree_id in rows]


def _category_subtree_cache_key(*, category_id: int, version: str) -> str:
    """Build a versioned Redis key for cached subtree ids."""
    return f"category_subtree:v{version}:root:{category_id}"


async def get_category_subtree_ids(session: AsyncSession, category_id: int) -> list[int]:
    """Return subtree ids using Redis cache for hot lookups when enabled."""
    settings = get_settings()
    redis_client = get_redis_client()
    if not settings.category_subtree_cache_enabled or redis_client is None:
        return await _query_category_subtree_ids(session, category_id)

    try:
        cache_version = await redis_client.get(_CATEGORY_SUBTREE_VERSION_KEY)
        version = cache_version or "1"
        cache_key = _category_subtree_cache_key(category_id=category_id, version=version)
        cached_payload = await redis_client.get(cache_key)

        if cached_payload:
            decoded = json.loads(cached_payload)
            if isinstance(decoded, list) and all(isinstance(item, int) for item in decoded):
                return decoded
            logger.warning(
                "category_subtree_cache_invalid_payload",
                extra={"cache_key": cache_key, "category_id": category_id},
            )

        subtree_ids = await _query_category_subtree_ids(session, category_id)
        await redis_client.set(
            cache_key,
            json.dumps(subtree_ids),
            ex=settings.category_subtree_cache_ttl_seconds,
        )
        return subtree_ids
    except (RedisError, ValueError, TypeError) as exc:
        logger.warning(
            "category_subtree_cache_unavailable",
            extra={"category_id": category_id, "error": str(exc)},
        )
        return await _query_category_subtree_ids(session, category_id)


async def invalidate_category_subtree_cache() -> None:
    """Invalidate subtree cache by bumping the global subtree cache version."""
    settings = get_settings()
    redis_client = get_redis_client()
    if not settings.category_subtree_cache_enabled or redis_client is None:
        return

    try:
        await redis_client.incr(_CATEGORY_SUBTREE_VERSION_KEY)
    except RedisError as exc:
        logger.warning("category_subtree_cache_invalidation_failed", extra={"error": str(exc)})


def _descendant_chain_cte(start_category_id: int, depth_limit: int | None = None):
    """Build a recursive CTE that walks from a category down to its deepest descendant."""
    descendant_chain: Select = (
        select(
            Category.id.label("id"),
            literal(1).label("depth"),
        )
        .where(Category.id == start_category_id)
        .cte(name="descendant_chain", recursive=True)
    )

    category_alias = Category.__table__.alias("desc_alias")
    recursive_step = select(
        category_alias.c.id,
        (descendant_chain.c.depth + 1).label("depth"),
    ).where(category_alias.c.parent_id == descendant_chain.c.id)

    if depth_limit is not None:
        recursive_step = recursive_step.where(descendant_chain.c.depth < depth_limit)

    return descendant_chain.union_all(recursive_step)


async def category_subtree_height(session: AsyncSession, category_id: int) -> int:
    """Compute the height of the subtree rooted at *category_id* (1 = leaf)."""
    descendant_chain = _descendant_chain_cte(category_id, depth_limit=MAX_CATEGORY_DEPTH + 1)
    height_statement = select(func.coalesce(func.max(descendant_chain.c.depth), 1))
    height = await timed_execute_scalar_one(session, height_statement)
    return int(height)


async def validate_category_parent(session: AsyncSession, parent_id: int) -> None:
    """Validate that a parent category exists and is within depth limits.

    Uses a single ancestor-chain CTE query to check both existence and depth.

    Raises:
        CategoryParentNotFoundError: if the parent does not exist.
        CategoryDepthError: if attaching here would exceed MAX_CATEGORY_DEPTH.
    """
    ancestor_chain = _ancestor_chain_cte(parent_id, depth_limit=MAX_CATEGORY_DEPTH + 1)
    stmt = select(func.max(ancestor_chain.c.depth))
    depth = await timed_execute_scalar_one(session, stmt)
    if depth is None:
        raise CategoryParentNotFoundError(parent_id)
    if depth >= MAX_CATEGORY_DEPTH:
        raise CategoryDepthError(MAX_CATEGORY_DEPTH)


async def validate_category_reparent(
    session: AsyncSession, category_id: int, new_parent_id: int | None
) -> None:
    """Validate re-parenting a category: parent exists, no cycles, depth within limits.

    Uses a single query combining ancestor-chain and descendant-chain CTEs
    to check parent existence, cycle detection, and depth limits in one
    database roundtrip (down from four).

    Raises:
        CategoryParentNotFoundError: if the new parent does not exist.
        CategoryCycleError: if the re-parent creates a cycle.
        CategoryDepthError: if the re-parent would exceed MAX_CATEGORY_DEPTH.
    """
    if new_parent_id is None:
        return

    ancestor_chain = _ancestor_chain_cte(new_parent_id, depth_limit=MAX_CATEGORY_DEPTH + 1)
    descendant_chain = _descendant_chain_cte(category_id, depth_limit=MAX_CATEGORY_DEPTH + 1)

    stmt = select(
        func.max(ancestor_chain.c.depth).label("parent_depth"),
        exists(
            select(1).select_from(ancestor_chain).where(ancestor_chain.c.id == category_id)
        ).label("has_cycle"),
        func.coalesce(func.max(descendant_chain.c.depth), 1).label("subtree_height"),
    )

    row = await timed_execute_one(session, stmt)

    if row.parent_depth is None:
        raise CategoryParentNotFoundError(new_parent_id)
    if row.has_cycle:
        raise CategoryCycleError("Category cycle detected")
    if row.parent_depth + row.subtree_height > MAX_CATEGORY_DEPTH:
        raise CategoryDepthError(MAX_CATEGORY_DEPTH)
