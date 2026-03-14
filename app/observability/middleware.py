from __future__ import annotations

import asyncio
import logging
from threading import Lock
from time import perf_counter
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.observability.context import (
    RequestObservabilityState,
    reset_current_request_state,
    set_current_request_state,
)
from app.observability.db import get_pool_in_use_connections
from app.observability.metrics import (
    http_errors_total,
    http_exceptions_total,
    http_request_duration_seconds,
    http_requests_total,
    http_requests_in_flight,
    http_response_payload_size_bytes,
    http_response_time_seconds,
)

_IN_FLIGHT_LOCK = Lock()
_IN_FLIGHT_REQUESTS = 0


def _add_in_flight(delta: int) -> int:
    global _IN_FLIGHT_REQUESTS
    with _IN_FLIGHT_LOCK:
        _IN_FLIGHT_REQUESTS += delta
        return _IN_FLIGHT_REQUESTS


def _get_in_flight() -> int:
    with _IN_FLIGHT_LOCK:
        return _IN_FLIGHT_REQUESTS


def _record_http_metrics(
    request_duration: float,
    payload_size: int,
    status_code: int,
    exception_class: str | None,
    method: str,
    route_path: str,
) -> None:
    """Record HTTP metrics on a thread-pool thread to avoid Prometheus scrape mutex contention."""
    attributes = {
        "http.method": method,
        "http.route": route_path,
        "http.status_code": str(status_code),
    }
    http_request_duration_seconds.record(request_duration, attributes)
    http_response_time_seconds.record(request_duration, attributes)
    http_response_payload_size_bytes.record(payload_size, attributes)
    http_requests_total.add(1, attributes)
    if status_code >= 400:
        http_errors_total.add(
            1,
            {
                **attributes,
                "http.status_class": f"{status_code // 100}xx",
                "error_type": _classify_error_type(status_code),
            },
        )
    if exception_class is not None:
        http_exceptions_total.add(
            1,
            {
                "http.method": method,
                "http.route": route_path,
                "exception_class": exception_class,
            },
        )


class ObservabilityMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.ingress_start = perf_counter()
        request_id = uuid4().hex
        request_state = RequestObservabilityState(request_id=request_id)
        request.state.request_observability_state = request_state
        request.state.request_id = request_id
        context_token = set_current_request_state(request_state)

        in_flight_attributes = {"http.method": request.method}
        http_requests_in_flight.add(1, in_flight_attributes)
        in_flight_requests = _add_in_flight(1)

        response: Response | None = None
        status_code = 500
        payload_size = 0
        exception_class: str | None = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id

            content_length = response.headers.get("content-length")
            if content_length is not None:
                payload_size = int(content_length)
            elif hasattr(response, "body") and isinstance(response.body, (bytes, bytearray)):
                payload_size = len(response.body)
            return response
        except Exception as exc:
            exception_class = exc.__class__.__name__
            raise
        finally:
            end_time = perf_counter()
            request_duration = end_time - request.state.ingress_start
            duration_ms = request_duration * 1000

            route = request.scope.get("route")
            route_path = getattr(route, "path", request.url.path)

            # Decrement in-flight counters synchronously — must reflect active request count.
            http_requests_in_flight.add(-1, in_flight_attributes)
            _add_in_flight(-1)

            # Schedule histogram/counter recording on a thread-pool thread to avoid
            # blocking the event loop on the Prometheus scrape mutex.
            asyncio.get_running_loop().run_in_executor(
                None,
                _record_http_metrics,
                request_duration, payload_size, status_code, exception_class,
                request.method, route_path,
            )

            request_logger = logging.getLogger("app.request")
            log_level = logging.INFO
            if status_code >= 500:
                log_level = logging.ERROR
            elif status_code >= 400:
                log_level = logging.WARNING

            queue_wait_ms = request_state.queue_wait_ms
            handler_ms = request_state.handler_ms
            db_time_ms = request_state.db_time_ms
            db_acquire_ms = request_state.db_acquire_ms
            db_execute_fetch_ms = request_state.db_execute_fetch_ms
            db_time_gap_ms = max(0.0, db_execute_fetch_ms - db_time_ms)

            request_logger.log(
                log_level,
                "request_completed",
                extra={
                    "request_id": request_id,
                    "http_method": request.method,
                    "http_route": route_path,
                    "http_path": request.url.path,
                    "http_status_code": status_code,
                    "duration_ms": round(duration_ms, 3),
                    "queue_wait_ms": round(queue_wait_ms, 3),
                    "handler_ms": round(handler_ms, 3),
                    "db_time_ms": round(db_time_ms, 3),
                    "db_acquire_ms": round(db_acquire_ms, 3),
                    "db_execute_fetch_ms": round(db_execute_fetch_ms, 3),
                    "db_time_gap_ms": round(db_time_gap_ms, 3),
                    "db_query_count": request_state.db_query_count,
                    "db_slowest_query_ms": round(request_state.db_slowest_query_ms, 3),
                    "db_slowest_query_name": request_state.db_slowest_query_name,
                    "db_pool_in_use": get_pool_in_use_connections(),
                    "in_flight_requests": _get_in_flight(),
                    "response_size_bytes": payload_size,
                    "client_ip": request.client.host if request.client else "",
                    "error_type": _classify_error_type(status_code) if status_code >= 400 else "",
                    "exception_class": exception_class or "",
                },
            )

            if duration_ms > 200:
                request_logger.warning(
                    "request_slow",
                    extra={
                        "request_id": request_id,
                        "http_method": request.method,
                        "http_route": route_path,
                        "http_path": request.url.path,
                        "http_status_code": status_code,
                        "duration_ms": round(duration_ms, 3),
                        "queue_wait_ms": round(queue_wait_ms, 3),
                        "handler_ms": round(handler_ms, 3),
                        "db_time_ms": round(db_time_ms, 3),
                        "db_acquire_ms": round(db_acquire_ms, 3),
                        "db_execute_fetch_ms": round(db_execute_fetch_ms, 3),
                        "db_time_gap_ms": round(db_time_gap_ms, 3),
                        "db_query_count": request_state.db_query_count,
                        "db_slowest_query_ms": round(request_state.db_slowest_query_ms, 3),
                        "db_slowest_query_name": request_state.db_slowest_query_name,
                        "db_pool_in_use": get_pool_in_use_connections(),
                        "in_flight_requests": in_flight_requests,
                        "search_filters_applied": request_state.search_filters_applied,
                        "search_phase_ms": {
                            key: round(value, 3)
                            for key, value in request_state.search_phase_ms.items()
                        },
                    },
                )

            reset_current_request_state(context_token)


def _classify_error_type(status_code: int) -> str:
    if status_code == 404:
        return "not_found"
    if status_code == 409:
        return "conflict"
    if status_code == 422:
        return "validation"
    if status_code >= 500:
        return "server_error"
    return "client_error"
