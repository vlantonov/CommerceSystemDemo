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
from app.db.session import get_session


@pytest.fixture
async def client(db_session: AsyncSession):
    """Create an AsyncClient with mocked dependency injection."""
    app = create_app()
    
    async def override_get_session():
        yield db_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """Test the health check endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_home_page_endpoint(client: AsyncClient):
    """Test that the root endpoint serves an HTML project overview page."""
    response = await client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Commerce System Demo" in response.text
    assert "/api/v1/search/products" in response.text


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
