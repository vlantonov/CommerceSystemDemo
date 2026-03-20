"""Unit tests for API handler branch and error behavior."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request

from app.api import categories as categories_api
from app.api import products as products_api
from app.api import search as search_api
from app.schemas.category import CategoryCreate, CategoryUpdate
from app.schemas.product import ProductCreate, ProductUpdate


def make_request() -> Request:
    """Build a minimal Starlette request for direct endpoint invocation."""
    return Request({"type": "http", "method": "GET", "path": "/"})


@pytest.mark.asyncio
async def test_create_category_parent_not_found_returns_404(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    payload = CategoryCreate(name="Child", parent_id=999)

    monkeypatch.setattr(
        categories_api,
        "validate_category_parent",
        AsyncMock(side_effect=categories_api.CategoryParentNotFoundError(999)),
    )

    with pytest.raises(HTTPException) as exc:
        await categories_api.create_category(payload=payload, session=session)

    assert exc.value.status_code == 404
    assert exc.value.detail == "Parent category not found"


@pytest.mark.asyncio
async def test_create_category_depth_exceeded_returns_422(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    payload = CategoryCreate(name="Child", parent_id=1)

    monkeypatch.setattr(
        categories_api,
        "validate_category_parent",
        AsyncMock(side_effect=categories_api.CategoryDepthError("too deep")),
    )

    with pytest.raises(HTTPException) as exc:
        await categories_api.create_category(payload=payload, session=session)

    assert exc.value.status_code == 422
    assert "Category depth cannot exceed" in exc.value.detail


@pytest.mark.asyncio
async def test_create_category_conflict_rolls_back(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))
    session.rollback = AsyncMock()

    payload = CategoryCreate(name="Duplicate", parent_id=None)

    with pytest.raises(HTTPException) as exc:
        await categories_api.create_category(payload=payload, session=session)

    assert exc.value.status_code == 409
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_category_success_returns_model(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    captured = {}

    async def refresh_side_effect(category):
        category.id = 55
        category.created_at = datetime.now(timezone.utc)
        category.updated_at = datetime.now(timezone.utc)
        captured["category"] = category

    session.refresh = AsyncMock(side_effect=refresh_side_effect)
    payload = CategoryCreate(name="Root", parent_id=None)

    result = await categories_api.create_category(payload=payload, session=session)

    assert result.id == 55
    assert result.name == "Root"
    assert captured["category"].name == "Root"


@pytest.mark.asyncio
async def test_get_category_success_returns_category(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    category = SimpleNamespace(
        id=7,
        name="Books",
        parent_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(categories_api, "get_category_or_none", AsyncMock(return_value=category))

    result = await categories_api.get_category(category_id=7, session=session)

    assert result.id == 7
    assert result.name == "Books"


@pytest.mark.asyncio
async def test_list_categories_uses_fast_total_path(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    records = [
        SimpleNamespace(
            id=1,
            name="One",
            parent_id=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    ]
    scalar_one = AsyncMock(return_value=999)

    monkeypatch.setattr(categories_api, "timed_execute_scalars_all", AsyncMock(return_value=records))
    monkeypatch.setattr(categories_api, "timed_execute_scalar_one", scalar_one)

    result = await categories_api.list_categories(limit=10, offset=0, session=session)

    assert result.total == 1
    assert len(result.items) == 1
    scalar_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_categories_uses_count_query_when_needed(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    records = [
        SimpleNamespace(
            id=1,
            name="One",
            parent_id=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    ]
    scalar_one = AsyncMock(return_value=42)

    monkeypatch.setattr(categories_api, "timed_execute_scalars_all", AsyncMock(return_value=records))
    monkeypatch.setattr(categories_api, "timed_execute_scalar_one", scalar_one)

    result = await categories_api.list_categories(limit=1, offset=5, session=session)

    assert result.total == 42
    scalar_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_category_not_found_returns_404(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    payload = CategoryUpdate(name="Renamed")

    monkeypatch.setattr(categories_api, "get_category_or_none", AsyncMock(return_value=None))

    with pytest.raises(HTTPException) as exc:
        await categories_api.update_category(category_id=123, payload=payload, session=session)

    assert exc.value.status_code == 404
    assert exc.value.detail == "Category not found"


@pytest.mark.asyncio
async def test_update_category_cycle_detected_returns_422(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    category = SimpleNamespace(id=10, name="Node", parent_id=None, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    payload = CategoryUpdate(parent_id=11)

    monkeypatch.setattr(categories_api, "get_category_or_none", AsyncMock(return_value=category))
    monkeypatch.setattr(
        categories_api,
        "validate_category_reparent",
        AsyncMock(side_effect=categories_api.CategoryCycleError("Category cycle detected")),
    )

    with pytest.raises(HTTPException) as exc:
        await categories_api.update_category(category_id=10, payload=payload, session=session)

    assert exc.value.status_code == 422
    assert exc.value.detail == "Category cycle detected"


@pytest.mark.asyncio
async def test_update_category_parent_not_found_returns_404(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    category = SimpleNamespace(
        id=10,
        name="Node",
        parent_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    payload = CategoryUpdate(parent_id=999)

    monkeypatch.setattr(categories_api, "get_category_or_none", AsyncMock(return_value=category))
    monkeypatch.setattr(
        categories_api,
        "validate_category_reparent",
        AsyncMock(side_effect=categories_api.CategoryParentNotFoundError(999)),
    )

    with pytest.raises(HTTPException) as exc:
        await categories_api.update_category(category_id=10, payload=payload, session=session)

    assert exc.value.status_code == 404
    assert exc.value.detail == "Parent category not found"


@pytest.mark.asyncio
async def test_update_category_depth_exceeded_returns_422(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    category = SimpleNamespace(
        id=11,
        name="Node",
        parent_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    payload = CategoryUpdate(parent_id=12)

    monkeypatch.setattr(categories_api, "get_category_or_none", AsyncMock(return_value=category))
    monkeypatch.setattr(
        categories_api,
        "validate_category_reparent",
        AsyncMock(side_effect=categories_api.CategoryDepthError("too deep")),
    )

    with pytest.raises(HTTPException) as exc:
        await categories_api.update_category(category_id=11, payload=payload, session=session)

    assert exc.value.status_code == 422
    assert "Category depth cannot exceed" in exc.value.detail


@pytest.mark.asyncio
async def test_update_category_success_sets_fields(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    category = SimpleNamespace(
        id=20,
        name="Old",
        parent_id=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    payload = CategoryUpdate(name="New", parent_id=2)

    monkeypatch.setattr(categories_api, "get_category_or_none", AsyncMock(return_value=category))
    monkeypatch.setattr(categories_api, "validate_category_reparent", AsyncMock(return_value=None))

    result = await categories_api.update_category(category_id=20, payload=payload, session=session)

    assert result.name == "New"
    assert result.parent_id == 2
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_category_not_found_returns_404(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    monkeypatch.setattr(categories_api, "get_category_or_none", AsyncMock(return_value=None))

    with pytest.raises(HTTPException) as exc:
        await categories_api.delete_category(category_id=1, session=session)

    assert exc.value.status_code == 404
    assert exc.value.detail == "Category not found"


@pytest.mark.asyncio
async def test_delete_category_success_commits(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    category = SimpleNamespace(id=1, name="DeleteMe")
    monkeypatch.setattr(categories_api, "get_category_or_none", AsyncMock(return_value=category))

    await categories_api.delete_category(category_id=1, session=session)

    session.delete.assert_awaited_once_with(category)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_product_conflict_rolls_back():
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))
    session.rollback = AsyncMock()
    payload = ProductCreate(
        title="Prod",
        description="Desc",
        sku="DUP-001",
        price=Decimal("10.00"),
        category_id=None,
    )

    with pytest.raises(HTTPException) as exc:
        await products_api.create_product(payload=payload, session=session)

    assert exc.value.status_code == 409
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_product_success_returns_model():
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    async def refresh_side_effect(product):
        product.id = 99
        product.created_at = datetime.now(timezone.utc)
        product.updated_at = datetime.now(timezone.utc)

    session.refresh = AsyncMock(side_effect=refresh_side_effect)

    payload = ProductCreate(
        title="Prod",
        description="Desc",
        sku="OK-001",
        price=Decimal("10.00"),
        category_id=None,
    )

    result = await products_api.create_product(payload=payload, session=session)

    assert result.id == 99
    assert result.sku == "OK-001"


@pytest.mark.asyncio
async def test_get_product_not_found_returns_404(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    monkeypatch.setattr(products_api, "timed_get", AsyncMock(return_value=None))

    with pytest.raises(HTTPException) as exc:
        await products_api.get_product(product_id=3, session=session)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_product_success_returns_product(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    product = SimpleNamespace(
        id=3,
        title="Prod",
        description="Desc",
        image_url=None,
        sku="GET-001",
        price=Decimal("11.00"),
        category_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(products_api, "timed_get", AsyncMock(return_value=product))

    result = await products_api.get_product(product_id=3, session=session)

    assert result.id == 3
    assert result.sku == "GET-001"


@pytest.mark.asyncio
async def test_list_products_fast_total_path(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    records = [
        SimpleNamespace(
            id=1,
            title="A",
            description="B",
            image_url=None,
            sku="A-001",
            price=Decimal("1.00"),
            category_id=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    ]
    scalar_one = AsyncMock(return_value=100)
    monkeypatch.setattr(products_api, "timed_execute_scalars_all", AsyncMock(return_value=records))
    monkeypatch.setattr(products_api, "timed_execute_scalar_one", scalar_one)

    result = await products_api.list_products(limit=10, offset=0, session=session)

    assert result.total == 1
    scalar_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_products_count_query_path(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    records = [
        SimpleNamespace(
            id=1,
            title="A",
            description="B",
            image_url=None,
            sku="A-001",
            price=Decimal("1.00"),
            category_id=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    ]
    scalar_one = AsyncMock(return_value=5)
    monkeypatch.setattr(products_api, "timed_execute_scalars_all", AsyncMock(return_value=records))
    monkeypatch.setattr(products_api, "timed_execute_scalar_one", scalar_one)

    result = await products_api.list_products(limit=1, offset=2, session=session)

    assert result.total == 5
    scalar_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_product_not_found_returns_404(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    payload = ProductUpdate(title="Renamed")
    monkeypatch.setattr(products_api, "timed_get", AsyncMock(return_value=None))

    with pytest.raises(HTTPException) as exc:
        await products_api.update_product(product_id=10, payload=payload, session=session)

    assert exc.value.status_code == 404
    assert exc.value.detail == "Product not found"


@pytest.mark.asyncio
async def test_update_product_conflict_returns_409(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    product = SimpleNamespace(
        id=5,
        title="Prod",
        description="Desc",
        image_url=None,
        sku="ORIG-001",
        price=Decimal("10.00"),
        category_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    payload = ProductUpdate(sku="NEW-001")

    monkeypatch.setattr(products_api, "timed_get", AsyncMock(return_value=product))
    session.commit = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))
    session.rollback = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await products_api.update_product(product_id=5, payload=payload, session=session)

    assert exc.value.status_code == 409
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_product_success_updates_fields(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    product = SimpleNamespace(
        id=5,
        title="Old",
        description="Desc",
        image_url=None,
        sku="OLD-001",
        price=Decimal("10.00"),
        category_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    payload = ProductUpdate(title="New", sku="NEW-001")

    monkeypatch.setattr(products_api, "timed_get", AsyncMock(return_value=product))

    result = await products_api.update_product(product_id=5, payload=payload, session=session)

    assert result.title == "New"
    assert result.sku == "NEW-001"
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_product_not_found_returns_404(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    monkeypatch.setattr(products_api, "timed_get", AsyncMock(return_value=None))

    with pytest.raises(HTTPException) as exc:
        await products_api.delete_product(product_id=404, session=session)

    assert exc.value.status_code == 404
    assert exc.value.detail == "Product not found"


@pytest.mark.asyncio
async def test_delete_product_success_commits(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    product = SimpleNamespace(id=8, sku="DEL-001")
    monkeypatch.setattr(products_api, "timed_get", AsyncMock(return_value=product))

    await products_api.delete_product(product_id=8, session=session)

    session.delete.assert_awaited_once_with(product)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_invalid_price_range_returns_422():
    request = make_request()
    session = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await search_api.search_products_endpoint(
            request=request,
            q=None,
            min_price=Decimal("10"),
            max_price=Decimal("1"),
            category_id=None,
            limit=20,
            offset=0,
            session=session,
        )

    assert exc.value.status_code == 422
    assert exc.value.detail == "min_price cannot be greater than max_price"


@pytest.mark.asyncio
async def test_search_sets_request_state_and_records_zero_results(monkeypatch: pytest.MonkeyPatch):
    request = make_request()
    request.state.request_observability_state = SimpleNamespace(
        search_phase_ms=None,
        search_filters_applied=None,
    )

    async def fake_search_products(**kwargs):
        kwargs["timing_context"]["query_ms"] = 3.2
        return [], 0

    monkeypatch.setattr(search_api, "search_products", fake_search_products)

    response = await search_api.search_products_endpoint(
        request=request,
        q="gaming",
        min_price=Decimal("100"),
        max_price=None,
        category_id=1,
        limit=10,
        offset=0,
        session=AsyncMock(),
    )

    assert response.total == 0
    assert response.items == []
    assert request.state.request_observability_state.search_phase_ms == {"query_ms": 3.2}
    assert request.state.request_observability_state.search_filters_applied == [
        "q",
        "min_price",
        "category_id",
    ]


@pytest.mark.asyncio
async def test_search_returns_product_response_items(monkeypatch: pytest.MonkeyPatch):
    request = make_request()
    product = SimpleNamespace(
        id=1,
        title="Gaming Laptop",
        description="High-end",
        image_url=None,
        sku="GAME-001",
        price=Decimal("1999.99"),
        category_id=2,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    async def fake_search_products(**kwargs):
        kwargs["timing_context"]["db_ms"] = 1.1
        return [product], 1

    monkeypatch.setattr(search_api, "search_products", fake_search_products)

    response = await search_api.search_products_endpoint(
        request=request,
        q="game",
        min_price=None,
        max_price=None,
        category_id=None,
        limit=20,
        offset=0,
        session=AsyncMock(),
    )

    assert response.total == 1
    assert len(response.items) == 1
    assert response.items[0].sku == "GAME-001"