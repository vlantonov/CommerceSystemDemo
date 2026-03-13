from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from time import perf_counter

from app.db.session import get_session_factory
from app.models.product import Product
from app.services.category_service import category_subtree_cte


async def search_products(
    session: AsyncSession,
    *,
    q: str | None,
    min_price,
    max_price,
    category_id: int | None,
    limit: int,
    offset: int,
    timing_context: dict[str, float] | None = None,
):
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

    # Fetch data first using LIMIT — this is always fast.
    data_query_start = perf_counter()
    records = (await session.execute(query.limit(limit).offset(offset))).scalars().all()
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
            total = (await count_session.execute(total_query)).scalar_one()
        timing_context["count_query_ms"] = (perf_counter() - count_query_start) * 1000

    return records, total
