"""Product business logic helpers and search orchestration."""

import re
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from time import perf_counter


def _escape_like(pattern: str) -> str:
    """Escape LIKE metacharacters (%, _, \\) so they match literally."""
    return re.sub(r"([%_\\])", r"\\\1", pattern)

from app.observability.db_timing import timed_execute_scalar_one, timed_execute_scalars_all
from app.models.product import Product
from app.services.category_service import category_subtree_cte


async def search_products(
    *,
    session: AsyncSession,
    q: str | None,
    min_price,
    max_price,
    category_id: int | None,
    limit: int,
    offset: int,
    timing_context: dict[str, float] | None = None,
):
    """Return filtered products and total count with phase timing telemetry."""
    timing_context = timing_context if timing_context is not None else {}

    query_build_start = perf_counter()
    query = select(Product)

    if q:
        normalized = q.upper()
        safe_q = _escape_like(q)
        query = query.where(or_(Product.title.ilike(f"%{safe_q}%"), Product.sku == normalized))

    if min_price is not None:
        query = query.where(Product.price >= min_price)

    if max_price is not None:
        query = query.where(Product.price <= max_price)

    if category_id is not None:
        category_tree = category_subtree_cte(category_id)
        query = query.where(Product.category_id.in_(select(category_tree.c.id)))

    query = query.order_by(Product.id)
    timing_context["query_build_ms"] = (perf_counter() - query_build_start) * 1000

    # Fetch data and count on the provided session for a consistent snapshot.
    data_query_start = perf_counter()
    records = await timed_execute_scalars_all(session, query.limit(limit).offset(offset))
    timing_context["data_query_ms"] = (perf_counter() - data_query_start) * 1000

    # Skip COUNT(*) when the total is inferrable from the result set.
    # If we're on the first page and fewer rows than the page limit were returned,
    # all matching rows fit on this page so total == offset + len(records).
    if offset == 0 and len(records) < limit:
        total = len(records)
        timing_context["count_query_ms"] = 0.0
    else:
        total_query = select(func.count()).select_from(query.subquery())
        count_query_start = perf_counter()
        total = await timed_execute_scalar_one(session, total_query)
        timing_context["count_query_ms"] = (perf_counter() - count_query_start) * 1000

    return records, total
