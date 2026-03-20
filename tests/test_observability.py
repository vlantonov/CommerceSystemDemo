"""Unit tests for observability middleware and metric emission paths."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request
from starlette.responses import Response

from app.api import categories as categories_api
from app.api import products as products_api
from app.api import search as search_api
from app.observability import middleware as middleware_mod
from app.schemas.category import CategoryCreate
from app.schemas.product import ProductCreate


def _build_request(path: str = "/x", method: str = "GET") -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "scheme": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


class _FakeLoop:
    def __init__(self):
        self.calls: list[tuple] = []

    def run_in_executor(self, executor, func, *args):
        self.calls.append((executor, func, args))
        func(*args)


def _metric_pair():
    return SimpleNamespace(add=MagicMock()), SimpleNamespace(record=MagicMock())


def test_record_http_metrics_success_path(monkeypatch: pytest.MonkeyPatch):
    http_errors_total, _ = _metric_pair()
    http_exceptions_total, _ = _metric_pair()
    http_requests_total, _ = _metric_pair()
    _, http_request_duration_seconds = _metric_pair()
    _, http_response_payload_size_bytes = _metric_pair()

    monkeypatch.setattr(middleware_mod, "http_errors_total", http_errors_total)
    monkeypatch.setattr(middleware_mod, "http_exceptions_total", http_exceptions_total)
    monkeypatch.setattr(middleware_mod, "http_requests_total", http_requests_total)
    monkeypatch.setattr(middleware_mod, "http_request_duration_seconds", http_request_duration_seconds)
    monkeypatch.setattr(middleware_mod, "http_response_payload_size_bytes", http_response_payload_size_bytes)

    middleware_mod._record_http_metrics(
        request_duration=0.123,
        payload_size=345,
        status_code=200,
        exception_class=None,
        method="GET",
        route_path="/health",
    )

    http_request_duration_seconds.record.assert_called_once()
    http_response_payload_size_bytes.record.assert_called_once()
    http_requests_total.add.assert_called_once()
    http_errors_total.add.assert_not_called()
    http_exceptions_total.add.assert_not_called()


def test_record_http_metrics_error_and_exception(monkeypatch: pytest.MonkeyPatch):
    http_errors_total, _ = _metric_pair()
    http_exceptions_total, _ = _metric_pair()
    http_requests_total, _ = _metric_pair()
    _, http_request_duration_seconds = _metric_pair()
    _, http_response_payload_size_bytes = _metric_pair()

    monkeypatch.setattr(middleware_mod, "http_errors_total", http_errors_total)
    monkeypatch.setattr(middleware_mod, "http_exceptions_total", http_exceptions_total)
    monkeypatch.setattr(middleware_mod, "http_requests_total", http_requests_total)
    monkeypatch.setattr(middleware_mod, "http_request_duration_seconds", http_request_duration_seconds)
    monkeypatch.setattr(middleware_mod, "http_response_payload_size_bytes", http_response_payload_size_bytes)

    middleware_mod._record_http_metrics(
        request_duration=0.2,
        payload_size=10,
        status_code=404,
        exception_class="RuntimeError",
        method="GET",
        route_path="/missing",
    )

    http_errors_total.add.assert_called_once()
    _, kwargs = http_errors_total.add.call_args
    assert kwargs == {}
    error_attrs = http_errors_total.add.call_args.args[1]
    assert error_attrs["error_type"] == "not_found"
    assert error_attrs["http.status_class"] == "4xx"

    http_exceptions_total.add.assert_called_once()
    exc_attrs = http_exceptions_total.add.call_args.args[1]
    assert exc_attrs["exception_class"] == "RuntimeError"


@pytest.mark.asyncio
async def test_middleware_dispatch_success_records_metrics(monkeypatch: pytest.MonkeyPatch):
    middleware_mod._IN_FLIGHT_REQUESTS = 0
    fake_loop = _FakeLoop()
    request_logger = MagicMock()

    http_requests_in_flight = SimpleNamespace(add=MagicMock())
    record_http_metrics = MagicMock()

    monkeypatch.setattr(middleware_mod, "http_requests_in_flight", http_requests_in_flight)
    monkeypatch.setattr(middleware_mod, "_record_http_metrics", record_http_metrics)
    monkeypatch.setattr(middleware_mod.asyncio, "get_running_loop", lambda: fake_loop)
    monkeypatch.setattr(middleware_mod, "get_pool_in_use_connections", lambda: 2)
    monkeypatch.setattr(middleware_mod.logging, "getLogger", lambda _name=None: request_logger)
    monkeypatch.setattr(middleware_mod, "uuid4", lambda: SimpleNamespace(hex="req-123"))
    monkeypatch.setattr(middleware_mod, "perf_counter", MagicMock(side_effect=[1.0, 1.1]))

    async def call_next(_request: Request):
        return Response(content=b"ok", status_code=200)

    request = _build_request(path="/health")
    middleware = middleware_mod.ObservabilityMetricsMiddleware(app=AsyncMock())
    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-123"
    assert middleware_mod._get_in_flight() == 0
    http_requests_in_flight.add.assert_any_call(1, {"http.method": "GET"})
    http_requests_in_flight.add.assert_any_call(-1, {"http.method": "GET"})
    assert fake_loop.calls
    record_http_metrics.assert_called_once()
    request_logger.log.assert_called_once()


@pytest.mark.asyncio
async def test_middleware_dispatch_exception_records_exception_class(monkeypatch: pytest.MonkeyPatch):
    middleware_mod._IN_FLIGHT_REQUESTS = 0
    fake_loop = _FakeLoop()
    request_logger = MagicMock()

    http_requests_in_flight = SimpleNamespace(add=MagicMock())
    record_http_metrics = MagicMock()

    monkeypatch.setattr(middleware_mod, "http_requests_in_flight", http_requests_in_flight)
    monkeypatch.setattr(middleware_mod, "_record_http_metrics", record_http_metrics)
    monkeypatch.setattr(middleware_mod.asyncio, "get_running_loop", lambda: fake_loop)
    monkeypatch.setattr(middleware_mod, "get_pool_in_use_connections", lambda: 0)
    monkeypatch.setattr(middleware_mod.logging, "getLogger", lambda _name=None: request_logger)
    monkeypatch.setattr(middleware_mod, "uuid4", lambda: SimpleNamespace(hex="req-err"))
    monkeypatch.setattr(middleware_mod, "perf_counter", MagicMock(side_effect=[5.0, 5.05]))

    async def call_next(_request: Request):
        raise RuntimeError("boom")

    middleware = middleware_mod.ObservabilityMetricsMiddleware(app=AsyncMock())
    with pytest.raises(RuntimeError, match="boom"):
        await middleware.dispatch(_build_request(path="/err"), call_next)

    assert middleware_mod._get_in_flight() == 0
    record_http_metrics.assert_called_once()
    args = record_http_metrics.call_args.args
    assert args[2] == 500
    assert args[3] == "RuntimeError"


@pytest.mark.asyncio
async def test_middleware_dispatch_slow_request_payload_body_fallback(monkeypatch: pytest.MonkeyPatch):
    middleware_mod._IN_FLIGHT_REQUESTS = 0
    fake_loop = _FakeLoop()
    request_logger = MagicMock()

    monkeypatch.setattr(middleware_mod, "http_requests_in_flight", SimpleNamespace(add=MagicMock()))
    monkeypatch.setattr(middleware_mod, "_record_http_metrics", MagicMock())
    monkeypatch.setattr(middleware_mod.asyncio, "get_running_loop", lambda: fake_loop)
    monkeypatch.setattr(middleware_mod, "get_pool_in_use_connections", lambda: 1)
    monkeypatch.setattr(middleware_mod.logging, "getLogger", lambda _name=None: request_logger)
    monkeypatch.setattr(middleware_mod, "uuid4", lambda: SimpleNamespace(hex="req-slow"))
    monkeypatch.setattr(middleware_mod, "perf_counter", MagicMock(side_effect=[10.0, 10.25]))

    async def call_next(_request: Request):
        response = Response(content=b"hello", status_code=404)
        del response.headers["content-length"]
        return response

    middleware = middleware_mod.ObservabilityMetricsMiddleware(app=AsyncMock())
    response = await middleware.dispatch(_build_request(path="/slow"), call_next)

    assert response.status_code == 404
    request_logger.warning.assert_called_once()
    warning_event = request_logger.warning.call_args.args[0]
    assert warning_event == "request_slow"


def test_classify_error_type_mapping():
    assert middleware_mod._classify_error_type(404) == "not_found"
    assert middleware_mod._classify_error_type(409) == "conflict"
    assert middleware_mod._classify_error_type(422) == "validation"
    assert middleware_mod._classify_error_type(500) == "server_error"
    assert middleware_mod._classify_error_type(401) == "client_error"


@pytest.mark.asyncio
async def test_search_endpoint_emits_search_metrics(monkeypatch: pytest.MonkeyPatch):
    add_requests = MagicMock()
    record_results = MagicMock()
    add_zero_results = MagicMock()

    monkeypatch.setattr(search_api, "search_requests_total", SimpleNamespace(add=add_requests))
    monkeypatch.setattr(search_api, "search_result_count", SimpleNamespace(record=record_results))
    monkeypatch.setattr(search_api, "search_zero_results_total", SimpleNamespace(add=add_zero_results))

    async def fake_search_products(**kwargs):
        kwargs["timing_context"]["db_ms"] = 1.5
        return [], 0

    monkeypatch.setattr(search_api, "search_products", fake_search_products)

    request = _build_request(path="/api/v1/products/search")
    response = await search_api.search_products_endpoint(
        request=request,
        q="abc",
        min_price=None,
        max_price=None,
        category_id=None,
        limit=10,
        offset=0,
        session=AsyncMock(),
    )

    assert response.total == 0
    add_requests.assert_called_once()
    record_results.assert_called_once_with(0, ANY)
    add_zero_results.assert_called_once()


@pytest.mark.asyncio
async def test_product_create_emits_success_metric(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    async def refresh_side_effect(product):
        product.id = 100
        product.created_at = datetime.now(timezone.utc)
        product.updated_at = datetime.now(timezone.utc)

    session.refresh = AsyncMock(side_effect=refresh_side_effect)

    add_mutation = MagicMock()
    monkeypatch.setattr(products_api, "product_mutations_total", SimpleNamespace(add=add_mutation))

    payload = ProductCreate(
        title="Laptop",
        description="desc",
        sku="LTP-001",
        price=Decimal("12.00"),
        category_id=None,
    )

    result = await products_api.create_product(payload=payload, session=session)

    assert result.id == 100
    add_mutation.assert_called_once_with(1, {"operation": "create", "result": "success"})


@pytest.mark.asyncio
async def test_product_create_emits_conflict_metric(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))
    session.rollback = AsyncMock()

    add_mutation = MagicMock()
    monkeypatch.setattr(products_api, "product_mutations_total", SimpleNamespace(add=add_mutation))

    payload = ProductCreate(
        title="Laptop",
        description="desc",
        sku="LTP-001",
        price=Decimal("12.00"),
        category_id=None,
    )

    with pytest.raises(HTTPException) as exc:
        await products_api.create_product(payload=payload, session=session)

    assert exc.value.status_code == 409
    add_mutation.assert_called_once_with(1, {"operation": "create", "result": "conflict"})


@pytest.mark.asyncio
async def test_category_create_parent_not_found_emits_validation_metrics(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    payload = CategoryCreate(name="Child", parent_id=321)

    validation_add = MagicMock()
    mutation_add = MagicMock()
    monkeypatch.setattr(
        categories_api,
        "category_validation_failures_total",
        SimpleNamespace(add=validation_add),
    )
    monkeypatch.setattr(categories_api, "category_mutations_total", SimpleNamespace(add=mutation_add))
    monkeypatch.setattr(
        categories_api,
        "validate_category_parent",
        AsyncMock(side_effect=categories_api.CategoryParentNotFoundError(321)),
    )

    with pytest.raises(HTTPException) as exc:
        await categories_api.create_category(payload=payload, session=session)

    assert exc.value.status_code == 404
    validation_add.assert_called_once_with(1, {"reason": "parent_not_found"})
    mutation_add.assert_called_once_with(1, {"operation": "create", "result": "parent_not_found"})