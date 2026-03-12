from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

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
):
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

    total_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(total_query)).scalar_one()

    records = (await session.execute(query.limit(limit).offset(offset))).scalars().all()
    return records, total
