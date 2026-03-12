from decimal import Decimal

import pytest

from app.models.category import Category
from app.models.product import Product
from app.services.product_service import search_products


async def seed_catalog(db_session):
    root = Category(name="Electronics")
    child = Category(name="Laptops", parent=root)
    other = Category(name="Books")

    db_session.add_all([root, child, other])
    await db_session.flush()

    products = [
        Product(
            title="Ultrabook X13",
            description="13-inch laptop",
            image_url="https://cdn.example.com/ultrabook-x13.webp",
            sku="UBX13-16-512",
            price=Decimal("1299.99"),
            category_id=child.id,
        ),
        Product(
            title="Gaming Tower",
            description="High-end desktop",
            image_url="https://cdn.example.com/gaming-tower.webp",
            sku="GT-4090",
            price=Decimal("2499.00"),
            category_id=root.id,
        ),
        Product(
            title="Python Cookbook",
            description="Book for Python developers",
            image_url="https://cdn.example.com/python-cookbook.webp",
            sku="BOOK-PY-01",
            price=Decimal("59.90"),
            category_id=other.id,
        ),
    ]
    db_session.add_all(products)
    await db_session.commit()

    return {"root": root.id, "child": child.id, "other": other.id}


@pytest.mark.asyncio
async def test_search_by_category_includes_descendants(db_session):
    ids = await seed_catalog(db_session)

    records, total = await search_products(
        db_session,
        q=None,
        min_price=None,
        max_price=None,
        category_id=ids["root"],
        limit=20,
        offset=0,
    )

    assert total == 2
    assert {item.sku for item in records} == {"UBX13-16-512", "GT-4090"}


@pytest.mark.asyncio
async def test_search_by_price_range_is_inclusive(db_session):
    await seed_catalog(db_session)

    records, total = await search_products(
        db_session,
        q=None,
        min_price=Decimal("59.90"),
        max_price=Decimal("1299.99"),
        category_id=None,
        limit=20,
        offset=0,
    )

    assert total == 2
    assert {item.sku for item in records} == {"UBX13-16-512", "BOOK-PY-01"}


@pytest.mark.asyncio
async def test_search_by_query_matches_title_or_exact_sku(db_session):
    await seed_catalog(db_session)

    title_records, title_total = await search_products(
        db_session,
        q="Ultrabook",
        min_price=None,
        max_price=None,
        category_id=None,
        limit=20,
        offset=0,
    )
    assert title_total == 1
    assert title_records[0].sku == "UBX13-16-512"

    sku_records, sku_total = await search_products(
        db_session,
        q="gt-4090",
        min_price=None,
        max_price=None,
        category_id=None,
        limit=20,
        offset=0,
    )
    assert sku_total == 1
    assert sku_records[0].sku == "GT-4090"


@pytest.mark.asyncio
async def test_search_pagination(db_session):
    await seed_catalog(db_session)

    page_one, total = await search_products(
        db_session,
        q=None,
        min_price=None,
        max_price=None,
        category_id=None,
        limit=2,
        offset=0,
    )
    page_two, total_second = await search_products(
        db_session,
        q=None,
        min_price=None,
        max_price=None,
        category_id=None,
        limit=2,
        offset=2,
    )

    assert total == 3
    assert total_second == 3
    assert len(page_one) == 2
    assert len(page_two) == 1
