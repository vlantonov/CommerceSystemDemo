from __future__ import annotations

import re
from time import perf_counter

from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from sqlalchemy import Engine, event

from app.observability.metrics import db_pool_in_use_connections, db_query_duration_seconds

_DB_TIME_KEY = "_commerce_db_query_start"
_INSTRUMENTED_ENGINES: set[int] = set()


def _extract_operation(statement: str) -> str:
    tokenized = statement.strip().split(maxsplit=1)
    if not tokenized:
        return "UNKNOWN"
    return tokenized[0].upper()


def _extract_table(statement: str, operation: str) -> str:
    patterns: dict[str, str] = {
        "SELECT": r"\\bFROM\\s+([\\w.\"]+)",
        "DELETE": r"\\bFROM\\s+([\\w.\"]+)",
        "INSERT": r"\\bINTO\\s+([\\w.\"]+)",
        "UPDATE": r"\\bUPDATE\\s+([\\w.\"]+)",
    }
    pattern = patterns.get(operation)
    if pattern is None:
        return "unknown"

    match = re.search(pattern, statement, flags=re.IGNORECASE)
    if match is None:
        return "unknown"
    return match.group(1).strip('"')


def instrument_engine(engine: Engine) -> None:
    engine_id = id(engine)
    if engine_id in _INSTRUMENTED_ENGINES:
        return

    SQLAlchemyInstrumentor().instrument(engine=engine)

    pool_attributes = {"db.pool.name": "default"}

    @event.listens_for(engine.pool, "checkout")
    def checkout(dbapi_connection, connection_record, connection_proxy):
        db_pool_in_use_connections.add(1, pool_attributes)

    @event.listens_for(engine.pool, "checkin")
    def checkin(dbapi_connection, connection_record):
        db_pool_in_use_connections.add(-1, pool_attributes)

    @event.listens_for(engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        start_times = conn.info.setdefault(_DB_TIME_KEY, [])
        start_times.append(perf_counter())

    @event.listens_for(engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        start_times = conn.info.get(_DB_TIME_KEY, [])
        if not start_times:
            return

        start = start_times.pop()
        duration = perf_counter() - start
        operation = _extract_operation(statement)
        table = _extract_table(statement, operation)
        db_query_duration_seconds.record(
            duration,
            {
                "db.system": "postgresql",
                "db.operation": operation,
                "db.table": table,
            },
        )

    _INSTRUMENTED_ENGINES.add(engine_id)
