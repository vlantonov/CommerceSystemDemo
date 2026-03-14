"""Product business logic helpers and search orchestration."""

from sqlalchemy import func, or_, select
from time import perf_counter

from app.db.session import get_session_factory
from app.observability.db_timing import timed_execute_scalar_one, timed_execute_scalars_all
from app.models.product import Product
from app.services.category_service import category_subtree_cte


async def search_products(
    *,
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
        query = query.where(or_(Product.title.ilike(f"%{q}%"), Product.sku == normalized))

    if min_price is not None:
        query = query.where(Product.price >= min_price)

    if max_price is not None:
        query = query.where(Product.price <= max_price)

    if category_id is not None:
        category_tree = category_subtree_cte(category_id)
        query = query.where(Product.category_id.in_(select(category_tree.c.id)))
    timing_context["query_build_ms"] = (perf_counter() - query_build_start) * 1000

    # Fetch data first, then release the connection back to the pool before COUNT.
    data_query_start = perf_counter()
    async with get_session_factory()() as data_session:
        records = await timed_execute_scalars_all(data_session, query.limit(limit).offset(offset))
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
        async with get_session_factory()() as count_session:
            total = await timed_execute_scalar_one(count_session, total_query)
        timing_context["count_query_ms"] = (perf_counter() - count_query_start) * 1000

    return records, total
