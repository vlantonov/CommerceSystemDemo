from __future__ import annotations

import json
import logging
import queue
import sys
from datetime import UTC, datetime
from logging.handlers import QueueHandler, QueueListener

from opentelemetry import trace

from app.core.config import Settings
from app.observability.context import get_current_request_state

_LOGGING_CONFIGURED = False
_log_queue: queue.SimpleQueue = queue.SimpleQueue()
_queue_listener: QueueListener | None = None


class _OpenTelemetryContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        request_state = get_current_request_state()
        record.request_id = request_state.request_id if request_state is not None else ""

        span = trace.get_current_span()
        span_context = span.get_span_context()

        if span_context.is_valid:
            record.trace_id = f"{span_context.trace_id:032x}"
            record.span_id = f"{span_context.span_id:016x}"
        else:
            record.trace_id = ""
            record.span_id = ""

        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", ""),
            "trace_id": getattr(record, "trace_id", ""),
            "span_id": getattr(record, "span_id", ""),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key.startswith("_"):
                continue
            if key in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "message",
                "asctime",
                "trace_id",
                "span_id",
                "request_id",
            }:
                continue

            if isinstance(value, (str, int, float, bool)) or value is None:
                payload[key] = value
            else:
                payload[key] = str(value)

        return json.dumps(payload, ensure_ascii=True)


def initialize_logging(settings: Settings) -> None:
    global _LOGGING_CONFIGURED, _queue_listener
    if _LOGGING_CONFIGURED:
        return

    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Blocking StreamHandler runs in the listener thread, off the event loop.
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(_JsonFormatter())
    stream_handler.setLevel(level)

    # QueueListener drains the queue in a dedicated daemon thread.
    _queue_listener = QueueListener(_log_queue, stream_handler, respect_handler_level=True)

    # QueueHandler: non-blocking enqueue in the caller's (event loop) thread.
    # Filter runs here so contextvars are captured in the correct thread.
    queue_handler = QueueHandler(_log_queue)
    queue_handler.addFilter(_OpenTelemetryContextFilter())
    queue_handler.setLevel(level)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    root.addHandler(queue_handler)

    # Keep uvicorn and app logs in the same structured format.
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "app"):
        lg = logging.getLogger(logger_name)
        lg.handlers.clear()
        lg.propagate = True

    _LOGGING_CONFIGURED = True


def start_log_listener() -> None:
    """Start the background thread that drains the log queue."""
    if _queue_listener is not None:
        _queue_listener.start()


def stop_log_listener() -> None:
    """Flush and stop the log listener thread gracefully."""
    if _queue_listener is not None:
        _queue_listener.stop()
