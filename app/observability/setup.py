"""Initialization helpers for tracing and metrics providers."""

from __future__ import annotations

from fastapi import FastAPI, Response
from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.observability.db import instrument_engine
from app.observability.logging import initialize_logging
from app.observability.middleware import ObservabilityMetricsMiddleware

_METRICS_PROVIDER_CONFIGURED = False
_TRACE_PROVIDER_CONFIGURED = False

# Focus histogram precision on sub-second latencies while keeping larger buckets
# for slow-path visibility.
_DURATION_BUCKET_BOUNDARIES_SECONDS: tuple[float, ...] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.075,
    0.1,
    0.15,
    0.2,
    0.3,
    0.5,
    0.75,
    1.0,
    1.5,
    2.0,
    3.0,
    5.0,
    7.5,
    10.0,
)


def _build_metric_views() -> list[View]:
    """Return metric views with explicit latency buckets for key histograms."""
    explicit_duration_aggregation = ExplicitBucketHistogramAggregation(
        boundaries=_DURATION_BUCKET_BOUNDARIES_SECONDS
    )
    return [
        View(
            instrument_name="commerce_http_request_duration_seconds",
            aggregation=explicit_duration_aggregation,
        ),
        View(
            instrument_name="commerce_http_processing_duration_seconds",
            aggregation=explicit_duration_aggregation,
        ),
        View(
            instrument_name="commerce_http_queue_wait_duration_seconds",
            aggregation=explicit_duration_aggregation,
        ),
        View(
            instrument_name="commerce_db_query_duration_seconds",
            aggregation=explicit_duration_aggregation,
        ),
    ]


def _build_resource(settings: Settings) -> Resource:
    """Build OpenTelemetry resource attributes from runtime settings."""
    attributes = {
        "service.name": settings.otel_service_name,
        "service.version": "0.2.0",
        "deployment.environment": settings.otel_environment,
    }

    if settings.otel_resource_attributes:
        for pair in settings.otel_resource_attributes.split(","):
            key, separator, value = pair.partition("=")
            if not separator:
                continue
            attributes[key.strip()] = value.strip()

    return Resource.create(attributes)


def _configure_metrics_provider(settings: Settings) -> None:
    """Initialize and register the OpenTelemetry metrics provider once."""
    global _METRICS_PROVIDER_CONFIGURED
    if _METRICS_PROVIDER_CONFIGURED:
        return

    resource = _build_resource(settings)
    metric_reader = PrometheusMetricReader()
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[metric_reader],
        views=_build_metric_views(),
    )
    metrics.set_meter_provider(meter_provider)
    _METRICS_PROVIDER_CONFIGURED = True


def _configure_trace_provider(settings: Settings) -> None:
    """Initialize and register the OpenTelemetry trace provider once."""
    global _TRACE_PROVIDER_CONFIGURED
    if _TRACE_PROVIDER_CONFIGURED:
        return

    if not settings.otel_exporter_otlp_endpoint:
        return

    resource = _build_resource(settings)
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_otlp_endpoint,
        insecure=settings.otel_exporter_otlp_insecure,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))

    from opentelemetry import trace

    trace.set_tracer_provider(provider)
    _TRACE_PROVIDER_CONFIGURED = True


def _add_metrics_endpoint(app: FastAPI, settings: Settings) -> None:
    """Expose a Prometheus scrape endpoint when metrics are enabled."""
    if not settings.otel_metrics_enabled:
        return

    if any(route.path == settings.otel_metrics_path for route in app.router.routes):
        return

    @app.get(settings.otel_metrics_path, include_in_schema=False)
    async def metrics_endpoint() -> Response:
        payload = generate_latest()
        return Response(content=payload, media_type=CONTENT_TYPE_LATEST)



def initialize_app_observability(app: FastAPI, settings: Settings) -> None:
    """Wire logging, metrics, tracing, and request middleware into the app."""
    initialize_logging(settings)

    if not settings.telemetry_enabled:
        return

    _configure_metrics_provider(settings)
    _configure_trace_provider(settings)
    _add_metrics_endpoint(app, settings)

    app.add_middleware(ObservabilityMetricsMiddleware)

    excluded_urls = settings.otel_trace_excluded_urls or settings.otel_metrics_path
    FastAPIInstrumentor.instrument_app(app, excluded_urls=excluded_urls)


def initialize_database_observability(engine: AsyncEngine, settings: Settings) -> None:
    """Attach database instrumentation hooks when telemetry is enabled."""
    if not settings.telemetry_enabled:
        return
    instrument_engine(engine.sync_engine)
