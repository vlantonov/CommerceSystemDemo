"""Integration benchmark tests for category hierarchy validations."""

from __future__ import annotations

from statistics import median
from time import perf_counter

import pytest

from app.models.category import Category
from app.observability.db_timing import timed_get
from app.services import category_service


async def _seed_linear_category_chain(
    db_session, depth: int
) -> tuple[int, int]:
    """Create a linear chain where each node points to the previous node."""
    categories = [
        Category(
            id=index,
            name=f"bench-cat-{index}",
            parent_id=(index - 1 if index > 1 else None),
        )
        for index in range(1, depth + 1)
    ]
    db_session.add_all(categories)
    await db_session.commit()
    return 1, depth


async def _old_category_depth(
    db_session,
    parent_id: int | None,
    max_depth: int = category_service.MAX_CATEGORY_DEPTH,
) -> int:
    """Baseline implementation: fetch one ancestor per query."""
    depth = 0
    current_parent_id = parent_id
    while current_parent_id is not None:
        depth += 1
        if depth > max_depth:
            return depth
        parent = await timed_get(db_session, Category, current_parent_id)
        if parent is None:
            break
        current_parent_id = parent.parent_id
    return depth


async def _old_validate_no_cycles(
    db_session, category_id: int, new_parent_id: int | None
) -> None:
    """Baseline implementation: walk ancestor chain one query at a time."""
    cursor = new_parent_id
    while cursor is not None:
        if cursor == category_id:
            raise ValueError("Category cycle detected")
        candidate = await timed_get(db_session, Category, cursor)
        if candidate is None:
            break
        cursor = candidate.parent_id


async def _benchmark_median_ms(
    fn,
    *args,
    iterations: int = 20,
    expect_exception: type[Exception] | None = None,
) -> float:
    """Return median per-call runtime in milliseconds for an async callable."""

    async def run_once() -> None:
        if expect_exception is None:
            await fn(*args)
            return
        try:
            await fn(*args)
        except expect_exception:
            return
        raise AssertionError(
            "Expected exception was not raised during benchmark run"
        )

    for _ in range(3):
        await run_once()

    samples_ms: list[float] = []
    for _ in range(iterations):
        started = perf_counter()
        await run_once()
        samples_ms.append((perf_counter() - started) * 1000)

    return float(median(samples_ms))


@pytest.mark.performance
@pytest.mark.asyncio
async def test_category_validation_cte_speedup_on_postgres(db_session):
    """Verify recursive CTE validation is faster than per-level queries."""
    depth = category_service.MAX_CATEGORY_DEPTH
    root_id, leaf_id = await _seed_linear_category_chain(
        db_session, depth=depth
    )

    # Sanity checks: both old and new implementations behave the same.
    assert await _old_category_depth(db_session, leaf_id) == depth
    assert await category_service.category_depth(db_session, leaf_id) == depth

    with pytest.raises(ValueError, match="Category cycle detected"):
        await _old_validate_no_cycles(
            db_session,
            category_id=root_id,
            new_parent_id=leaf_id,
        )

    with pytest.raises(ValueError, match="Category cycle detected"):
        await category_service.validate_no_cycles(
            db_session,
            category_id=root_id,
            new_parent_id=leaf_id,
        )

    old_depth_ms = await _benchmark_median_ms(
        _old_category_depth,
        db_session,
        leaf_id,
        iterations=20,
    )
    new_depth_ms = await _benchmark_median_ms(
        category_service.category_depth,
        db_session,
        leaf_id,
        iterations=20,
    )

    old_cycle_ms = await _benchmark_median_ms(
        _old_validate_no_cycles,
        db_session,
        root_id,
        leaf_id,
        iterations=20,
        expect_exception=ValueError,
    )
    new_cycle_ms = await _benchmark_median_ms(
        category_service.validate_no_cycles,
        db_session,
        root_id,
        leaf_id,
        iterations=20,
        expect_exception=ValueError,
    )

    depth_speedup = old_depth_ms / max(new_depth_ms, 0.001)
    cycle_speedup = old_cycle_ms / max(new_cycle_ms, 0.001)

    assert depth_speedup >= 2.0, (
        "Expected CTE depth validation to be at least 2x faster on PostgreSQL."
        " "
        f"old={old_depth_ms:.3f}ms new={new_depth_ms:.3f}ms "
        f"speedup={depth_speedup:.2f}x"
    )
    assert cycle_speedup >= 2.0, (
        "Expected CTE cycle validation to be at least 2x faster on PostgreSQL."
        " "
        f"old={old_cycle_ms:.3f}ms new={new_cycle_ms:.3f}ms "
        f"speedup={cycle_speedup:.2f}x"
    )
