from __future__ import annotations

from time import perf_counter

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.observability.metrics import (
    http_errors_total,
    http_exceptions_total,
    http_request_duration_seconds,
    http_requests_total,
    http_requests_in_flight,
    http_response_payload_size_bytes,
    http_response_time_seconds,
)


class ObservabilityMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.ingress_start = perf_counter()
        in_flight_attributes = {"http.method": request.method}
        http_requests_in_flight.add(1, in_flight_attributes)

        response: Response | None = None
        status_code = 500
        payload_size = 0
        exception_class: str | None = None
        try:
            response = await call_next(request)
            status_code = response.status_code

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

            route = request.scope.get("route")
            route_path = getattr(route, "path", request.url.path)

            attributes = {
                "http.method": request.method,
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
                        "http.method": request.method,
                        "http.route": route_path,
                        "exception_class": exception_class,
                    },
                )

            http_requests_in_flight.add(-1, in_flight_attributes)


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
