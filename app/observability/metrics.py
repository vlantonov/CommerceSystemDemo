"""Prometheus metric definitions for API and database activity."""

from opentelemetry import metrics
from opentelemetry.metrics import Counter, Histogram, UpDownCounter

_meter = metrics.get_meter("commerce-system-demo-observability", version="0.1.2")

http_request_duration_seconds: Histogram = _meter.create_histogram(
    name="commerce_http_request_duration_seconds",
    unit="s",
    description="End-to-end HTTP request duration from ingress to response ready",
)

http_processing_duration_seconds: Histogram = _meter.create_histogram(
    name="commerce_http_processing_duration_seconds",
    unit="s",
    description="Route handler processing duration",
)

http_queue_wait_duration_seconds: Histogram = _meter.create_histogram(
    name="commerce_http_queue_wait_duration_seconds",
    unit="s",
    description="Time spent waiting before route handler processing starts",
)

http_response_payload_size_bytes: Histogram = _meter.create_histogram(
    name="commerce_http_response_payload_size_bytes",
    unit="By",
    description="HTTP response payload size in bytes",
)

db_query_duration_seconds: Histogram = _meter.create_histogram(
    name="commerce_db_query_duration_seconds",
    unit="s",
    description="Database query execution duration",
)

http_requests_total: Counter = _meter.create_counter(
    name="commerce_http_requests_total",
    unit="1",
    description="Total number of processed HTTP requests",
)

http_requests_in_flight: UpDownCounter = _meter.create_up_down_counter(
    name="commerce_http_requests_in_flight",
    unit="1",
    description="Number of HTTP requests currently being processed",
)

http_errors_total: Counter = _meter.create_counter(
    name="commerce_http_errors_total",
    unit="1",
    description="Total number of HTTP error responses",
)

http_exceptions_total: Counter = _meter.create_counter(
    name="commerce_http_exceptions_total",
    unit="1",
    description="Total number of unhandled exceptions raised during HTTP processing",
)

db_pool_in_use_connections: UpDownCounter = _meter.create_up_down_counter(
    name="commerce_db_pool_in_use_connections",
    unit="1",
    description="Number of database connections currently checked out from the pool",
)

search_requests_total: Counter = _meter.create_counter(
    name="commerce_search_requests_total",
    unit="1",
    description="Total number of product search requests",
)

search_result_count: Histogram = _meter.create_histogram(
    name="commerce_search_result_count",
    unit="1",
    description="Number of results returned by product search",
)

search_zero_results_total: Counter = _meter.create_counter(
    name="commerce_search_zero_results_total",
    unit="1",
    description="Total number of product search requests that returned zero results",
)

product_mutations_total: Counter = _meter.create_counter(
    name="commerce_product_mutations_total",
    unit="1",
    description="Total number of product mutation operations",
)

category_mutations_total: Counter = _meter.create_counter(
    name="commerce_category_mutations_total",
    unit="1",
    description="Total number of category mutation operations",
)

category_validation_failures_total: Counter = _meter.create_counter(
    name="commerce_category_validation_failures_total",
    unit="1",
    description="Total number of category validation failures",
)

health_check_total: Counter = _meter.create_counter(
    name="commerce_health_check_total",
    unit="1",
    description="Total number of health check requests",
)

health_check_duration_seconds: Histogram = _meter.create_histogram(
    name="commerce_health_check_duration_seconds",
    unit="s",
    description="Duration of health check requests including database probe",
)
