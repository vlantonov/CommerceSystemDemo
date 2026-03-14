from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field


@dataclass
class RequestObservabilityState:
    request_id: str
    route_path: str = ""
    queue_wait_ms: float = 0.0
    handler_ms: float = 0.0
    db_time_ms: float = 0.0
    db_acquire_ms: float = 0.0
    db_execute_fetch_ms: float = 0.0
    db_query_count: int = 0
    db_slowest_query_ms: float = 0.0
    db_slowest_query_name: str = ""
    search_phase_ms: dict[str, float] = field(default_factory=dict)
    search_filters_applied: list[str] = field(default_factory=list)


_CURRENT_REQUEST_STATE: ContextVar[RequestObservabilityState | None] = ContextVar(
    "commerce_request_observability_state",
    default=None,
)


def set_current_request_state(state: RequestObservabilityState) -> Token[RequestObservabilityState | None]:
    return _CURRENT_REQUEST_STATE.set(state)


def reset_current_request_state(token: Token[RequestObservabilityState | None]) -> None:
    _CURRENT_REQUEST_STATE.reset(token)


def get_current_request_state() -> RequestObservabilityState | None:
    return _CURRENT_REQUEST_STATE.get()
