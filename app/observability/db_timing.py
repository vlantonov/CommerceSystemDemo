"""Helpers for measuring database call timings."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.observability.context import get_current_request_state


async def _record_connection_acquire(session: AsyncSession) -> None:
    """Measure pool checkout and connection acquire time for the current request."""
    acquire_start = perf_counter()
    await session.connection()
    acquire_ms = (perf_counter() - acquire_start) * 1000

    request_state = get_current_request_state()
    if request_state is not None:
        request_state.db_acquire_ms += acquire_ms


def _record_execute_fetch(duration_ms: float) -> None:
    """Accumulate execute-plus-fetch duration for the active request."""
    request_state = get_current_request_state()
    if request_state is not None:
        request_state.db_execute_fetch_ms += duration_ms


async def timed_get(session: AsyncSession, model: Any, ident: Any):
    """Run `session.get` while recording acquire and execution timings."""
    await _record_connection_acquire(session)
    execute_fetch_start = perf_counter()
    result = await session.get(model, ident)
    _record_execute_fetch((perf_counter() - execute_fetch_start) * 1000)
    return result


async def timed_execute_scalars_all(session: AsyncSession, statement: Any):
    """Execute a query and return all scalar rows with timing telemetry."""
    await _record_connection_acquire(session)
    execute_fetch_start = perf_counter()
    result = (await session.execute(statement)).scalars().all()
    _record_execute_fetch((perf_counter() - execute_fetch_start) * 1000)
    return result


async def timed_execute_all(session: AsyncSession, statement: Any):
    """Execute a query and return all rows (as tuples) with timing telemetry."""
    await _record_connection_acquire(session)
    execute_fetch_start = perf_counter()
    result = (await session.execute(statement)).all()
    _record_execute_fetch((perf_counter() - execute_fetch_start) * 1000)
    return result


async def timed_execute_scalar_one(session: AsyncSession, statement: Any):
    """Execute a query and return one scalar result with timing telemetry."""
    await _record_connection_acquire(session)
    execute_fetch_start = perf_counter()
    result = (await session.execute(statement)).scalar_one()
    _record_execute_fetch((perf_counter() - execute_fetch_start) * 1000)
    return result
