"""Concurrent access integration tests."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_engine, get_session, get_session_factory
from app.main import create_app


@pytest.fixture
async def concurrent_client(db_session):
    """Create a test client that gives each request an independent DB session."""
    app = create_app()
    session_factory = get_session_factory()

    app.state.engine = get_engine()
    app.state.session_factory = session_factory

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_concurrent_product_create_same_sku_one_conflicts(concurrent_client: AsyncClient):
    """Two concurrent creates with the same SKU should produce one conflict."""

    async def create_product():
        return await concurrent_client.post(
            "/api/v1/products",
            json={
                "title": "Concurrent Product",
                "description": "Concurrent create test",
                "sku": "RACE-SKU-001",
                "price": "99.99",
            },
        )

    response_a, response_b = await asyncio.gather(create_product(), create_product())

    status_codes = sorted([response_a.status_code, response_b.status_code])
    assert status_codes == [201, 409]


@pytest.mark.asyncio
async def test_concurrent_sibling_category_create_one_conflicts(concurrent_client: AsyncClient):
    """Two concurrent sibling category creates should produce one conflict."""

    parent_response = await concurrent_client.post("/api/v1/categories", json={"name": "Parent For Race"})
    assert parent_response.status_code == 201
    parent_id = parent_response.json()["id"]

    async def create_sibling():
        return await concurrent_client.post(
            "/api/v1/categories",
            json={"name": "Duplicate Child", "parent_id": parent_id},
        )

    response_a, response_b = await asyncio.gather(create_sibling(), create_sibling())

    status_codes = sorted([response_a.status_code, response_b.status_code])
    assert status_codes == [201, 409]


@pytest.mark.asyncio
async def test_concurrent_product_update_to_same_sku_one_conflicts(concurrent_client: AsyncClient):
    """Two concurrent updates to the same target SKU should produce one conflict."""

    create_a = await concurrent_client.post(
        "/api/v1/products",
        json={
            "title": "Product A",
            "description": "A",
            "sku": "RACE-UPD-A",
            "price": "10.00",
        },
    )
    create_b = await concurrent_client.post(
        "/api/v1/products",
        json={
            "title": "Product B",
            "description": "B",
            "sku": "RACE-UPD-B",
            "price": "20.00",
        },
    )
    assert create_a.status_code == 201
    assert create_b.status_code == 201

    product_a_id = create_a.json()["id"]
    product_b_id = create_b.json()["id"]

    async def update_to_shared_sku(product_id: int):
        return await concurrent_client.patch(
            f"/api/v1/products/{product_id}",
            json={"sku": "RACE-UPD-TARGET"},
        )

    response_a, response_b = await asyncio.gather(
        update_to_shared_sku(product_a_id),
        update_to_shared_sku(product_b_id),
    )

    status_codes = sorted([response_a.status_code, response_b.status_code])
    assert status_codes == [200, 409]


@pytest.mark.asyncio
async def test_concurrent_delete_same_product_one_not_found(concurrent_client: AsyncClient):
    """Two concurrent deletes may return 204/404 or 204/204 depending on timing."""

    created = await concurrent_client.post(
        "/api/v1/products",
        json={
            "title": "Delete Race",
            "description": "Delete me",
            "sku": "RACE-DEL-001",
            "price": "30.00",
        },
    )
    assert created.status_code == 201
    product_id = created.json()["id"]

    async def delete_once():
        return await concurrent_client.delete(f"/api/v1/products/{product_id}")

    response_a, response_b = await asyncio.gather(delete_once(), delete_once())

    status_codes = sorted([response_a.status_code, response_b.status_code])
    assert status_codes in ([204, 204], [204, 404])