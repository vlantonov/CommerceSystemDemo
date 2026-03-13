from __future__ import annotations

from time import perf_counter

from fastapi.routing import APIRoute
from starlette.requests import Request

from app.observability.metrics import http_processing_duration_seconds, http_queue_wait_duration_seconds


class ObservabilityRoute(APIRoute):
    def get_route_handler(self):
        original_route_handler = super().get_route_handler()

        async def traced_route_handler(request: Request):
            ingress_time = getattr(request.state, "ingress_start", perf_counter())
            handler_start = perf_counter()

            route = request.scope.get("route")
            route_path = getattr(route, "path", request.url.path)
            attributes = {
                "http.method": request.method,
                "http.route": route_path,
            }

            http_queue_wait_duration_seconds.record(handler_start - ingress_time, attributes)

            try:
                return await original_route_handler(request)
            finally:
                processing_duration = perf_counter() - handler_start
                request.state.processing_time_s = processing_duration
                http_processing_duration_seconds.record(processing_duration, attributes)

        return traced_route_handler
