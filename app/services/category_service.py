from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.observability.db_timing import timed_get

MAX_CATEGORY_DEPTH = 100


async def get_category_or_none(session: AsyncSession, category_id: int) -> Category | None:
    return await timed_get(session, Category, category_id)


async def category_depth(session: AsyncSession, parent_id: int | None) -> int:
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
    cursor = new_parent_id
    while cursor is not None:
        if cursor == category_id:
            raise ValueError("Category cycle detected")
        candidate = await timed_get(session, Category, cursor)
        if candidate is None:
            break
        cursor = candidate.parent_id


def category_subtree_cte(root_category_id: int):
    category_tree: Select = select(Category.id).where(Category.id == root_category_id).cte(
        name="category_tree", recursive=True
    )
    category_alias = Category.__table__.alias("category_alias")
    category_tree = category_tree.union_all(
        select(category_alias.c.id).where(category_alias.c.parent_id == category_tree.c.id)
    )
    return category_tree
