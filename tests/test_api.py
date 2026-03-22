"""
Integration tests for FastAPI endpoints using httpx AsyncClient.

Tests all CRUD operations for categories and products,
including error cases and validation.
"""

import pytest
from decimal import Decimal
from httpx import AsyncClient, ASGITransport
from jinja2 import TemplateNotFound
from sqlalchemy.ext.asyncio import AsyncSession

from app import main as app_main
from app.main import create_app
from app.db.session import get_engine, get_session, get_session_factory


@pytest.fixture
async def client(db_session: AsyncSession):
    """Create an AsyncClient with mocked dependency injection."""
    app = create_app()

    # httpx ASGITransport does not trigger ASGI lifespan, so populate
    # app.state with the engine / factory that conftest already initialised.
    app.state.engine = get_engine()
    app.state.session_factory = get_session_factory()
    
    async def override_get_session():
        yield db_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """Test the health check endpoint returns ok with database available."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "available"


@pytest.mark.asyncio
async def test_health_endpoint_database_unavailable(db_session: AsyncSession):
    """Test the health check reports error after all retries are exhausted."""
    from unittest.mock import AsyncMock

    app = create_app()

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    mock_engine = AsyncMock()
    mock_engine.connect = AsyncMock(side_effect=Exception("connection refused"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        app.state.engine = mock_engine
        response = await ac.get("/health")

    app.dependency_overrides.clear()

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "error"
    assert data["database"] == "unavailable"
    # Default retries is 3 — engine.connect should be called 3 times
    assert mock_engine.connect.call_count == 3


@pytest.mark.asyncio
async def test_health_endpoint_database_recovers_on_retry(db_session: AsyncSession):
    """Test that health check succeeds when DB fails first then recovers."""
    from unittest.mock import AsyncMock, MagicMock

    app = create_app()

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    # First call fails, second call succeeds
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value=None)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    mock_engine = AsyncMock()
    mock_engine.connect = MagicMock(
        side_effect=[Exception("transient error"), MagicMock(
            __aenter__=AsyncMock(return_value=mock_conn),
            __aexit__=AsyncMock(return_value=False),
        )]
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        app.state.engine = mock_engine
        response = await ac.get("/health")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "available"
    assert mock_engine.connect.call_count == 2


@pytest.mark.asyncio
async def test_health_endpoint_metrics_recorded_on_success(db_session: AsyncSession):
    """Test that health check metrics are recorded on successful check."""
    from unittest.mock import MagicMock, patch

    app = create_app()

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    app.state.engine = get_engine()
    app.state.session_factory = get_session_factory()

    mock_counter = MagicMock()
    mock_histogram = MagicMock()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch("app.observability.metrics.health_check_total", mock_counter), \
             patch("app.observability.metrics.health_check_duration_seconds", mock_histogram):
            response = await ac.get("/health")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    mock_counter.add.assert_called_once_with(1, {"status": "ok"})
    mock_histogram.record.assert_called_once()
    record_args = mock_histogram.record.call_args
    assert record_args[0][1] == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_endpoint_metrics_recorded_on_failure(db_session: AsyncSession):
    """Test that health check metrics are recorded on DB failure."""
    from unittest.mock import AsyncMock, MagicMock, patch

    app = create_app()

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    mock_engine = AsyncMock()
    mock_engine.connect = AsyncMock(side_effect=Exception("connection refused"))

    mock_counter = MagicMock()
    mock_histogram = MagicMock()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        app.state.engine = mock_engine
        with patch("app.observability.metrics.health_check_total", mock_counter), \
             patch("app.observability.metrics.health_check_duration_seconds", mock_histogram):
            response = await ac.get("/health")

    app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["status"] == "error"
    mock_counter.add.assert_called_once_with(1, {"status": "error"})
    mock_histogram.record.assert_called_once()
    record_args = mock_histogram.record.call_args
    assert record_args[1] == {"status": "error"} or record_args[0][1] == {"status": "error"}


@pytest.mark.asyncio
async def test_home_page_endpoint(client: AsyncClient):
    """Test that the root endpoint serves an HTML project overview page."""
    response = await client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Commerce System Demo" in response.text
    assert "/api/v1/products/search" in response.text


@pytest.mark.asyncio
async def test_home_page_endpoint_falls_back_when_template_missing(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """Test that root endpoint returns fallback page on missing template."""

    def raise_template_not_found(*args, **kwargs):
        raise TemplateNotFound("index.html")

    monkeypatch.setattr(
        app_main.templates,
        "TemplateResponse",
        raise_template_not_found,
    )

    response = await client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Template not available in this deployment" in response.text
    assert "/docs" in response.text


# ============================================================================
# Category Endpoints Tests
# ============================================================================

@pytest.mark.asyncio
async def test_create_category(client: AsyncClient):
    """Test creating a root category."""
    response = await client.post(
        "/api/v1/categories",
        json={"name": "Electronics"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Electronics"
    assert data["parent_id"] is None
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_create_category_with_parent(client: AsyncClient, db_session: AsyncSession):
    """Test creating a subcategory under a parent."""
    # Create parent
    parent_response = await client.post(
        "/api/v1/categories",
        json={"name": "Electronics"}
    )
    parent_id = parent_response.json()["id"]
    
    # Create child
    response = await client.post(
        "/api/v1/categories",
        json={"name": "Laptops", "parent_id": parent_id}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Laptops"
    assert data["parent_id"] == parent_id


@pytest.mark.asyncio
async def test_create_duplicate_sibling_category_fails(client: AsyncClient):
    """Test that duplicate sibling category names are rejected."""
    parent_response = await client.post(
        "/api/v1/categories",
        json={"name": "Electronics"}
    )
    parent_id = parent_response.json()["id"]
    
    # Create first sibling
    await client.post(
        "/api/v1/categories",
        json={"name": "Laptops", "parent_id": parent_id}
    )
    
    # Try to create duplicate sibling
    response = await client.post(
        "/api/v1/categories",
        json={"name": "Laptops", "parent_id": parent_id}
    )
    assert response.status_code == 409  # Conflict


@pytest.mark.asyncio
async def test_get_category(client: AsyncClient):
    """Test retrieving a category by ID."""
    create_response = await client.post(
        "/api/v1/categories",
        json={"name": "Electronics"}
    )
    category_id = create_response.json()["id"]
    
    response = await client.get(f"/api/v1/categories/{category_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == category_id
    assert data["name"] == "Electronics"


@pytest.mark.asyncio
async def test_get_nonexistent_category(client: AsyncClient):
    """Test that getting a nonexistent category returns 404."""
    response = await client.get("/api/v1/categories/99999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_categories(client: AsyncClient):
    """Test listing categories with pagination."""
    # Create a few categories
    for i in range(3):
        await client.post("/api/v1/categories", json={"name": f"Category{i}"})
    
    response = await client.get("/api/v1/categories?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 10
    assert data["offset"] == 0
    assert data["total"] >= 3
    assert len(data["items"]) >= 3


@pytest.mark.asyncio
async def test_update_category_name(client: AsyncClient):
    """Test updating a category's name."""
    create_response = await client.post(
        "/api/v1/categories",
        json={"name": "Old Name"}
    )
    category_id = create_response.json()["id"]
    
    response = await client.patch(
        f"/api/v1/categories/{category_id}",
        json={"name": "New Name"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Name"
    assert data["id"] == category_id


@pytest.mark.asyncio
async def test_update_category_parent(client: AsyncClient):
    """Test moving a category to a different parent."""
    # Create parents
    parent1 = (await client.post("/api/v1/categories", json={"name": "Parent1"})).json()["id"]
    parent2 = (await client.post("/api/v1/categories", json={"name": "Parent2"})).json()["id"]
    
    # Create child under parent1
    child = (await client.post(
        "/api/v1/categories",
        json={"name": "Child", "parent_id": parent1}
    )).json()
    
    # Move child to parent2
    response = await client.patch(
        f"/api/v1/categories/{child['id']}",
        json={"parent_id": parent2}
    )
    assert response.status_code == 200
    assert response.json()["parent_id"] == parent2


@pytest.mark.asyncio
async def test_delete_category(client: AsyncClient):
    """Test deleting a category."""
    create_response = await client.post(
        "/api/v1/categories",
        json={"name": "To Delete"}
    )
    category_id = create_response.json()["id"]
    
    response = await client.delete(f"/api/v1/categories/{category_id}")
    assert response.status_code == 204
    
    # Verify it's deleted
    check = await client.get(f"/api/v1/categories/{category_id}")
    assert check.status_code == 404


@pytest.mark.asyncio
async def test_delete_category_deletes_children(client: AsyncClient):
    """Test that deleting a parent category deletes all children."""
    parent = (await client.post("/api/v1/categories", json={"name": "Parent"})).json()["id"]
    child = (await client.post(
        "/api/v1/categories",
        json={"name": "Child", "parent_id": parent}
    )).json()["id"]
    
    # Delete parent
    await client.delete(f"/api/v1/categories/{parent}")
    
    # Verify child is also deleted
    response = await client.get(f"/api/v1/categories/{child}")
    assert response.status_code == 404


# ============================================================================
# Product Endpoints Tests
# ============================================================================

@pytest.mark.asyncio
async def test_create_product(client: AsyncClient):
    """Test creating a product."""
    response = await client.post(
        "/api/v1/products",
        json={
            "title": "Test Laptop",
            "description": "A test laptop",
            "sku": "TEST-001",
            "price": "999.99"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Laptop"
    assert data["sku"] == "TEST-001"
    assert data["price"] == "999.99"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_product_with_lowercase_sku_normalized(client: AsyncClient):
    """Test that SKU is normalized to uppercase."""
    response = await client.post(
        "/api/v1/products",
        json={
            "title": "Test",
            "description": "Test",
            "sku": "test-sku",
            "price": "100.00"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "TEST-SKU"


@pytest.mark.asyncio
async def test_create_product_invalid_sku_format(client: AsyncClient):
    """Test that invalid SKU format is rejected."""
    response = await client.post(
        "/api/v1/products",
        json={
            "title": "Test",
            "description": "Test",
            "sku": "invalid sku!",  # Contains space and special char
            "price": "100.00"
        }
    )
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_create_duplicate_sku_fails(client: AsyncClient):
    """Test that duplicate SKU is rejected."""
    # Create first product
    await client.post(
        "/api/v1/products",
        json={
            "title": "Product 1",
            "description": "Test",
            "sku": "UNIQUE-001",
            "price": "100.00"
        }
    )
    
    # Try to create with same SKU
    response = await client.post(
        "/api/v1/products",
        json={
            "title": "Product 2",
            "description": "Test",
            "sku": "UNIQUE-001",
            "price": "200.00"
        }
    )
    assert response.status_code == 409  # Conflict


@pytest.mark.asyncio
async def test_create_product_with_category(client: AsyncClient):
    """Test creating a product with a category."""
    category = (await client.post(
        "/api/v1/categories",
        json={"name": "Laptops"}
    )).json()
    
    response = await client.post(
        "/api/v1/products",
        json={
            "title": "Test Laptop",
            "description": "A test",
            "sku": "CAT-TEST-001",
            "price": "999.99",
            "category_id": category["id"]
        }
    )
    assert response.status_code == 201
    assert response.json()["category_id"] == category["id"]


@pytest.mark.asyncio
async def test_get_product(client: AsyncClient):
    """Test retrieving a product by ID."""
    create_response = await client.post(
        "/api/v1/products",
        json={
            "title": "Test",
            "description": "Test",
            "sku": "GET-TEST-001",
            "price": "500.00"
        }
    )
    product_id = create_response.json()["id"]
    
    response = await client.get(f"/api/v1/products/{product_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == product_id
    assert data["sku"] == "GET-TEST-001"


@pytest.mark.asyncio
async def test_get_nonexistent_product(client: AsyncClient):
    """Test that getting a nonexistent product returns 404."""
    response = await client.get("/api/v1/products/99999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_products(client: AsyncClient):
    """Test listing products with pagination."""
    for i in range(3):
        await client.post(
            "/api/v1/products",
            json={
                "title": f"Product {i}",
                "description": "Test",
                "sku": f"LIST-{i:03d}",
                "price": f"{100 + i * 50}.00"
            }
        )
    
    response = await client.get("/api/v1/products?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 10
    assert data["offset"] == 0
    assert data["total"] >= 3
    assert len(data["items"]) >= 3


@pytest.mark.asyncio
async def test_update_product(client: AsyncClient):
    """Test updating a product."""
    create_response = await client.post(
        "/api/v1/products",
        json={
            "title": "Old Title",
            "description": "Old description",
            "sku": "UPDATE-001",
            "price": "100.00"
        }
    )
    product_id = create_response.json()["id"]
    
    response = await client.patch(
        f"/api/v1/products/{product_id}",
        json={
            "title": "New Title",
            "price": "200.00"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "New Title"
    assert data["price"] == "200.00"
    assert data["sku"] == "UPDATE-001"  # SKU unchanged


@pytest.mark.asyncio
async def test_delete_product(client: AsyncClient):
    """Test deleting a product."""
    create_response = await client.post(
        "/api/v1/products",
        json={
            "title": "To Delete",
            "description": "Test",
            "sku": "DELETE-001",
            "price": "100.00"
        }
    )
    product_id = create_response.json()["id"]
    
    response = await client.delete(f"/api/v1/products/{product_id}")
    assert response.status_code == 204
    
    # Verify it's deleted
    check = await client.get(f"/api/v1/products/{product_id}")
    assert check.status_code == 404


@pytest.mark.asyncio
async def test_delete_category_unlinks_products(client: AsyncClient):
    """Test that deleting a category unlinks its products."""
    category = (await client.post(
        "/api/v1/categories",
        json={"name": "To Delete"}
    )).json()
    
    product = (await client.post(
        "/api/v1/products",
        json={
            "title": "Test",
            "description": "Test",
            "sku": "UNLINK-001",
            "price": "100.00",
            "category_id": category["id"]
        }
    )).json()
    
    # Delete the category
    await client.delete(f"/api/v1/categories/{category['id']}")
    
    # Check that product still exists but category_id is NULL
    response = await client.get(f"/api/v1/products/{product['id']}")
    assert response.status_code == 200
    assert response.json()["category_id"] is None


# ============================================================================
# Search Endpoint Tests
# ============================================================================

@pytest.mark.asyncio
async def test_search_by_title(client: AsyncClient):
    """Test searching products by title."""
    await client.post(
        "/api/v1/products",
        json={
            "title": "Unique Laptop Model X",
            "description": "A laptop",
            "sku": "SEARCH-TITLE-001",
            "price": "1000.00"
        }
    )
    
    response = await client.get("/api/v1/products/search?q=unique")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert any("Unique" in item["title"] for item in data["items"])


@pytest.mark.asyncio
async def test_search_by_sku(client: AsyncClient):
    """Test searching products by exact SKU."""
    await client.post(
        "/api/v1/products",
        json={
            "title": "Test Product",
            "description": "A product",
            "sku": "SEARCH-SKU-EXACT",
            "price": "500.00"
        }
    )
    
    response = await client.get("/api/v1/products/search?q=search-sku-exact")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["items"][0]["sku"] == "SEARCH-SKU-EXACT"


@pytest.mark.asyncio
async def test_search_by_price_range(client: AsyncClient):
    """Test searching products by price range."""
    for price in [100.00, 200.00, 300.00, 400.00]:
        await client.post(
            "/api/v1/products",
            json={
                "title": f"Product {price}",
                "description": "Test",
                "sku": f"PRICE-{price:.0f}",
                "price": f"{price:.2f}"
            }
        )
    
    response = await client.get("/api/v1/products/search?min_price=150.00&max_price=350.00")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 2
    for item in data["items"]:
        price = Decimal(item["price"])
        assert Decimal("150") <= price <= Decimal("350")


@pytest.mark.asyncio
async def test_search_by_category(client: AsyncClient):
    """Test searching products by category (including descendants)."""
    parent_cat = (await client.post(
        "/api/v1/categories",
        json={"name": "Parent"}
    )).json()
    
    child_cat = (await client.post(
        "/api/v1/categories",
        json={"name": "Child", "parent_id": parent_cat["id"]}
    )).json()
    
    # Create products in both categories
    await client.post(
        "/api/v1/products",
        json={
            "title": "Parent Product",
            "description": "Test",
            "sku": "CAT-PARENT-001",
            "price": "100.00",
            "category_id": parent_cat["id"]
        }
    )
    
    await client.post(
        "/api/v1/products",
        json={
            "title": "Child Product",
            "description": "Test",
            "sku": "CAT-CHILD-001",
            "price": "100.00",
            "category_id": child_cat["id"]
        }
    )
    
    # Search by parent category should return both
    response = await client.get(f"/api/v1/products/search?category_id={parent_cat['id']}")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_search_combined_filters(client: AsyncClient):
    """Test searching with multiple filters combined."""
    category = (await client.post(
        "/api/v1/categories",
        json={"name": "Electronics"}
    )).json()
    
    await client.post(
        "/api/v1/products",
        json={
            "title": "Gaming Laptop Pro",
            "description": "High-performance",
            "sku": "GAME-LAPTOP-001",
            "price": "2500.00",
            "category_id": category["id"]
        }
    )
    
    response = await client.get(
        f"/api/v1/products/search?q=gaming&min_price=2000&max_price=3000&category_id={category['id']}"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    item = data["items"][0]
    assert "Gaming" in item["title"]
    assert Decimal("2000") <= Decimal(item["price"]) <= Decimal("3000")


@pytest.mark.asyncio
async def test_search_pagination(client: AsyncClient):
    """Test search pagination."""
    for i in range(5):
        await client.post(
            "/api/v1/products",
            json={
                "title": f"Paginated {i}",
                "description": "Test",
                "sku": f"PAGE-{i:03d}",
                "price": f"{100 + i}.00"
            }
        )
    
    # Get first 2 items
    response1 = await client.get("/api/v1/products/search?limit=2&offset=0")
    assert response1.status_code == 200
    data1 = response1.json()
    assert len(data1["items"]) == 2
    assert data1["limit"] == 2
    assert data1["offset"] == 0
    
    # Get next 2 items
    response2 = await client.get("/api/v1/products/search?limit=2&offset=2")
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["items"]) == 2
    assert data2["offset"] == 2
    
    # Ensure pagination is working (different items)
    ids1 = [item["id"] for item in data1["items"]]
    ids2 = [item["id"] for item in data2["items"]]
    assert not set(ids1).intersection(set(ids2))


@pytest.mark.asyncio
async def test_search_invalid_price_range(client: AsyncClient):
    """Test that invalid price range (min > max) is rejected."""
    response = await client.get("/api/v1/products/search?min_price=1000&max_price=100")
    assert response.status_code == 422  # Validation error


# ============================================================================
# Whitespace Validation Tests
# ============================================================================

@pytest.mark.asyncio
async def test_create_category_with_space_only_name_fails(client: AsyncClient):
    """Test that creating a category with space-only name is rejected."""
    response = await client.post(
        "/api/v1/categories",
        json={"name": "   "}
    )
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_create_category_with_leading_trailing_spaces_stripped(client: AsyncClient):
    """Test that category names have leading/trailing spaces stripped."""
    response = await client.post(
        "/api/v1/categories",
        json={"name": "  Electronics  "}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Electronics"


@pytest.mark.asyncio
async def test_update_category_with_space_only_name_fails(client: AsyncClient):
    """Test that updating a category with space-only name is rejected."""
    create_response = await client.post(
        "/api/v1/categories",
        json={"name": "Original Name"}
    )
    category_id = create_response.json()["id"]
    
    response = await client.patch(
        f"/api/v1/categories/{category_id}",
        json={"name": "   "}
    )
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_create_product_with_space_only_title_fails(client: AsyncClient):
    """Test that creating a product with space-only title is rejected."""
    response = await client.post(
        "/api/v1/products",
        json={
            "title": "   ",
            "description": "Test description",
            "sku": "TEST-001",
            "price": "100.00"
        }
    )
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_create_product_with_space_only_description_fails(client: AsyncClient):
    """Test that creating a product with space-only description is rejected."""
    response = await client.post(
        "/api/v1/products",
        json={
            "title": "Test Product",
            "description": "   ",
            "sku": "TEST-001",
            "price": "100.00"
        }
    )
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_create_product_with_leading_trailing_spaces_stripped(client: AsyncClient):
    """Test that product title and description have leading/trailing spaces stripped."""
    response = await client.post(
        "/api/v1/products",
        json={
            "title": "  Test Product  ",
            "description": "  Test description  ",
            "sku": "TEST-001",
            "price": "100.00"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Product"
    assert data["description"] == "Test description"


@pytest.mark.asyncio
async def test_update_product_with_space_only_title_fails(client: AsyncClient):
    """Test that updating a product with space-only title is rejected."""
    create_response = await client.post(
        "/api/v1/products",
        json={
            "title": "Original Title",
            "description": "Test description",
            "sku": "TEST-001",
            "price": "100.00"
        }
    )
    product_id = create_response.json()["id"]
    
    response = await client.patch(
        f"/api/v1/products/{product_id}",
        json={"title": "   "}
    )
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_update_product_with_space_only_description_fails(client: AsyncClient):
    """Test that updating a product with space-only description is rejected."""
    create_response = await client.post(
        "/api/v1/products",
        json={
            "title": "Original Title",
            "description": "Original description",
            "sku": "TEST-001",
            "price": "100.00"
        }
    )
    product_id = create_response.json()["id"]
    
    response = await client.patch(
        f"/api/v1/products/{product_id}",
        json={"description": "   "}
    )
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_update_product_set_category_to_null(client: AsyncClient):
    """Test that explicitly sending category_id=null clears the category link."""
    cat_resp = await client.post("/api/v1/categories", json={"name": "Temp Cat"})
    category_id = cat_resp.json()["id"]

    create_resp = await client.post(
        "/api/v1/products",
        json={
            "title": "Linked Product",
            "description": "Has category",
            "sku": "NULLCAT-001",
            "price": "50.00",
            "category_id": category_id,
        },
    )
    product_id = create_resp.json()["id"]
    assert create_resp.json()["category_id"] == category_id

    response = await client.patch(
        f"/api/v1/products/{product_id}",
        json={"category_id": None},
    )
    assert response.status_code == 200
    assert response.json()["category_id"] is None


@pytest.mark.asyncio
async def test_update_product_set_image_url_to_null(client: AsyncClient):
    """Test that explicitly sending image_url=null clears the image."""
    create_resp = await client.post(
        "/api/v1/products",
        json={
            "title": "With Image",
            "description": "Has image",
            "sku": "NULLIMG-001",
            "price": "75.00",
            "image_url": "https://example.com/img.png",
        },
    )
    product_id = create_resp.json()["id"]
    assert create_resp.json()["image_url"] is not None

    response = await client.patch(
        f"/api/v1/products/{product_id}",
        json={"image_url": None},
    )
    assert response.status_code == 200
    assert response.json()["image_url"] is None


@pytest.mark.asyncio
async def test_update_product_omitted_fields_unchanged(client: AsyncClient):
    """Test that omitting fields from PATCH leaves them unchanged."""
    create_resp = await client.post(
        "/api/v1/products",
        json={
            "title": "Original",
            "description": "Keep this",
            "sku": "OMIT-001",
            "price": "99.00",
            "image_url": "https://example.com/keep.png",
        },
    )
    product_id = create_resp.json()["id"]

    response = await client.patch(
        f"/api/v1/products/{product_id}",
        json={"title": "Changed Only Title"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Changed Only Title"
    assert data["description"] == "Keep this"
    assert data["sku"] == "OMIT-001"
    assert data["price"] == "99.00"
    assert data["image_url"] == "https://example.com/keep.png"


# ============================================================================
# Category Depth Limit Tests
# ============================================================================

@pytest.mark.asyncio
async def test_create_category_exceeding_depth_limit(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    """Test that creating a category chain beyond MAX_CATEGORY_DEPTH is rejected."""
    from app.services import category_service as cs

    monkeypatch.setattr(cs, "MAX_CATEGORY_DEPTH", 3)

    # Build chain: root → L1 → L2 (depth 3)
    root = (await client.post("/api/v1/categories", json={"name": "Depth-Root"})).json()
    l1 = (await client.post("/api/v1/categories", json={"name": "Depth-L1", "parent_id": root["id"]})).json()
    l2 = (await client.post("/api/v1/categories", json={"name": "Depth-L2", "parent_id": l1["id"]})).json()
    assert l2["parent_id"] == l1["id"]

    # L3 should be rejected — depth would be 4 > 3
    response = await client.post(
        "/api/v1/categories",
        json={"name": "Depth-L3", "parent_id": l2["id"]},
    )
    assert response.status_code == 422
    assert "depth" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reparent_category_exceeding_depth_limit(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    """Test that re-parenting a subtree so combined depth exceeds the limit is rejected."""
    from app.services import category_service as cs

    monkeypatch.setattr(cs, "MAX_CATEGORY_DEPTH", 4)

    # Chain A: A1 → A2 → A3 (height 3)
    a1 = (await client.post("/api/v1/categories", json={"name": "ChainA-1"})).json()
    a2 = (await client.post("/api/v1/categories", json={"name": "ChainA-2", "parent_id": a1["id"]})).json()
    a3 = (await client.post("/api/v1/categories", json={"name": "ChainA-3", "parent_id": a2["id"]})).json()

    # Chain B: B1 → B2 (depth 2)
    b1 = (await client.post("/api/v1/categories", json={"name": "ChainB-1"})).json()
    b2 = (await client.post("/api/v1/categories", json={"name": "ChainB-2", "parent_id": b1["id"]})).json()

    # Try to move A1 under B2 → depth would be 2 + 3 = 5 > 4
    response = await client.patch(
        f"/api/v1/categories/{a1['id']}",
        json={"parent_id": b2["id"]},
    )
    assert response.status_code == 422
    assert "depth" in response.json()["detail"].lower()


# ============================================================================
# Category Cycle Detection Tests
# ============================================================================

@pytest.mark.asyncio
async def test_reparent_category_creating_cycle_rejected(client: AsyncClient):
    """Test that re-parenting a parent under its own child is rejected as a cycle."""
    parent = (await client.post("/api/v1/categories", json={"name": "Cycle-Parent"})).json()
    child = (await client.post(
        "/api/v1/categories",
        json={"name": "Cycle-Child", "parent_id": parent["id"]},
    )).json()

    # Try to make the parent a child of its own child → cycle
    response = await client.patch(
        f"/api/v1/categories/{parent['id']}",
        json={"parent_id": child["id"]},
    )
    assert response.status_code == 422
    assert "cycle" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reparent_category_creating_deep_cycle_rejected(client: AsyncClient):
    """Test that a cycle through multiple levels is detected and rejected."""
    a = (await client.post("/api/v1/categories", json={"name": "CycleDeep-A"})).json()
    b = (await client.post("/api/v1/categories", json={"name": "CycleDeep-B", "parent_id": a["id"]})).json()
    c = (await client.post("/api/v1/categories", json={"name": "CycleDeep-C", "parent_id": b["id"]})).json()

    # Try to make A a child of C → A→B→C→A cycle
    response = await client.patch(
        f"/api/v1/categories/{a['id']}",
        json={"parent_id": c["id"]},
    )
    assert response.status_code == 422
    assert "cycle" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reparent_category_self_reference_rejected(client: AsyncClient):
    """Test that setting a category as its own parent is rejected."""
    cat = (await client.post("/api/v1/categories", json={"name": "Self-Ref"})).json()

    response = await client.patch(
        f"/api/v1/categories/{cat['id']}",
        json={"parent_id": cat["id"]},
    )
    assert response.status_code == 422
    assert "cycle" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reparent_to_nonexistent_parent_rejected(client: AsyncClient):
    """Test that re-parenting to a nonexistent category returns 404."""
    cat = (await client.post("/api/v1/categories", json={"name": "Orphan-Move"})).json()

    response = await client.patch(
        f"/api/v1/categories/{cat['id']}",
        json={"parent_id": 99999},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_category_with_nonexistent_parent_rejected(client: AsyncClient):
    """Test that creating a category under a nonexistent parent returns 404."""
    response = await client.post(
        "/api/v1/categories",
        json={"name": "No-Parent", "parent_id": 99999},
    )
    assert response.status_code == 404


# ============================================================================
# LIKE Wildcard Injection Tests
# ============================================================================

@pytest.mark.asyncio
async def test_search_with_percent_wildcard_does_not_match_all(client: AsyncClient):
    """Test that a search query containing '%' does not act as a LIKE wildcard."""
    await client.post(
        "/api/v1/products",
        json={
            "title": "Specific Widget",
            "description": "Only this should NOT match",
            "sku": "LIKE-SAFE-001",
            "price": "10.00",
        },
    )

    # Searching for literal '%' should not match arbitrary products
    response = await client.get("/api/v1/products/search?q=%25")
    assert response.status_code == 200
    data = response.json()
    # '%' as a literal character shouldn't match "Specific Widget"
    for item in data["items"]:
        assert "%" in item["title"] or "%" in item["sku"]


@pytest.mark.asyncio
async def test_search_with_underscore_wildcard_does_not_match_single_char(client: AsyncClient):
    """Test that a search query containing '_' does not act as a single-char wildcard."""
    await client.post(
        "/api/v1/products",
        json={
            "title": "ABC",
            "description": "Three letter title",
            "sku": "LIKE-UNDER-001",
            "price": "10.00",
        },
    )

    # '_B_' as LIKE wildcards would match 'ABC', but as literal it should not
    response = await client.get("/api/v1/products/search?q=_B_")
    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert "_B_" in item["title"] or "_B_" in item["sku"].upper()


@pytest.mark.asyncio
async def test_search_with_backslash_is_safe(client: AsyncClient):
    """Test that a search query containing backslash doesn't cause errors."""
    response = await client.get("/api/v1/products/search?q=test%5Cvalue")
    assert response.status_code == 200
