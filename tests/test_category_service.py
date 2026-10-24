"""Unit tests for category service helper functions."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import category_service


@pytest.mark.asyncio
async def test_category_depth_stops_when_parent_missing(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    timed_execute_scalar_one = AsyncMock(return_value=1)
    monkeypatch.setattr(category_service, "timed_execute_scalar_one", timed_execute_scalar_one)

    depth = await category_service.category_depth(session, parent_id=1)
    assert depth == 1
    timed_execute_scalar_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_category_depth_returns_zero_for_none_parent(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    timed_execute_scalar_one = AsyncMock()
    monkeypatch.setattr(category_service, "timed_execute_scalar_one", timed_execute_scalar_one)

    depth = await category_service.category_depth(session, parent_id=None)

    assert depth == 0
    timed_execute_scalar_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_validate_no_cycles_raises_for_cycle(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    timed_execute_scalar_one = AsyncMock(return_value=1)
    monkeypatch.setattr(category_service, "timed_execute_scalar_one", timed_execute_scalar_one)

    with pytest.raises(ValueError, match="Category cycle detected"):
        await category_service.validate_no_cycles(session, category_id=1, new_parent_id=2)

    timed_execute_scalar_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_validate_category_parent_raises_not_found(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    # NULL max-depth from ancestor CTE means parent doesn't exist
    monkeypatch.setattr(category_service, "timed_execute_scalar_one", AsyncMock(return_value=None))

    with pytest.raises(category_service.CategoryParentNotFoundError):
        await category_service.validate_category_parent(session, parent_id=99)


@pytest.mark.asyncio
async def test_validate_category_parent_raises_depth_error(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    monkeypatch.setattr(
        category_service,
        "timed_execute_scalar_one",
        AsyncMock(return_value=category_service.MAX_CATEGORY_DEPTH),
    )

    with pytest.raises(category_service.CategoryDepthError):
        await category_service.validate_category_parent(session, parent_id=1)


@pytest.mark.asyncio
async def test_validate_category_reparent_returns_for_none_parent():
    session = AsyncMock()
    await category_service.validate_category_reparent(session, category_id=1, new_parent_id=None)


@pytest.mark.asyncio
async def test_validate_category_reparent_raises_parent_not_found(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    # parent_depth=None means parent doesn't exist
    monkeypatch.setattr(
        category_service,
        "timed_execute_one",
        AsyncMock(return_value=SimpleNamespace(parent_depth=None, has_cycle=False, subtree_height=1)),
    )

    with pytest.raises(category_service.CategoryParentNotFoundError):
        await category_service.validate_category_reparent(session, category_id=1, new_parent_id=77)


@pytest.mark.asyncio
async def test_validate_category_reparent_raises_cycle_error(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    monkeypatch.setattr(
        category_service,
        "timed_execute_one",
        AsyncMock(return_value=SimpleNamespace(parent_depth=5, has_cycle=True, subtree_height=1)),
    )

    with pytest.raises(category_service.CategoryCycleError, match="Category cycle detected"):
        await category_service.validate_category_reparent(session, category_id=1, new_parent_id=2)


@pytest.mark.asyncio
async def test_validate_category_reparent_raises_depth_error(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    monkeypatch.setattr(
        category_service,
        "timed_execute_one",
        AsyncMock(return_value=SimpleNamespace(
            parent_depth=category_service.MAX_CATEGORY_DEPTH,
            has_cycle=False,
            subtree_height=1,
        )),
    )

    with pytest.raises(category_service.CategoryDepthError):
        await category_service.validate_category_reparent(session, category_id=1, new_parent_id=2)


@pytest.mark.asyncio
async def test_validate_category_reparent_raises_depth_error_for_deep_subtree(monkeypatch: pytest.MonkeyPatch):
    """Moving a category with a deep subtree under a parent should fail if combined depth exceeds limit."""
    session = AsyncMock()
    # Parent depth alone is fine (90 < 100), but subtree adds 15 → 90 + 15 = 105 > 100
    monkeypatch.setattr(
        category_service,
        "timed_execute_one",
        AsyncMock(return_value=SimpleNamespace(parent_depth=90, has_cycle=False, subtree_height=15)),
    )

    with pytest.raises(category_service.CategoryDepthError):
        await category_service.validate_category_reparent(session, category_id=1, new_parent_id=2)


@pytest.mark.asyncio
async def test_validate_category_reparent_allows_when_combined_depth_fits(monkeypatch: pytest.MonkeyPatch):
    """Moving a category succeeds when parent depth + subtree height fits within limit."""
    session = AsyncMock()
    # Parent depth 90, subtree height 10 → 90 + 10 = 100 <= 100 → OK
    monkeypatch.setattr(
        category_service,
        "timed_execute_one",
        AsyncMock(return_value=SimpleNamespace(parent_depth=90, has_cycle=False, subtree_height=10)),
    )

    # Should not raise
    await category_service.validate_category_reparent(session, category_id=1, new_parent_id=2)


@pytest.mark.asyncio
async def test_category_depth_returns_when_exceeding_max(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    monkeypatch.setattr(
        category_service,
        "timed_execute_scalar_one",
        AsyncMock(return_value=category_service.MAX_CATEGORY_DEPTH + 1),
    )

    depth = await category_service.category_depth(session, parent_id=1)
    assert depth == category_service.MAX_CATEGORY_DEPTH + 1


@pytest.mark.asyncio
async def test_validate_no_cycles_breaks_on_missing_candidate(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    monkeypatch.setattr(category_service, "timed_execute_scalar_one", AsyncMock(return_value=0))

    await category_service.validate_no_cycles(session, category_id=1, new_parent_id=2)


@pytest.mark.asyncio
async def test_get_category_subtree_ids_cache_miss_stores_result(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    redis_client = AsyncMock()
    redis_client.get = AsyncMock(side_effect=[None, None])
    redis_client.set = AsyncMock()

    cache_hits_add = MagicMock()
    cache_misses_add = MagicMock()

    monkeypatch.setattr(
        category_service,
        "get_settings",
        lambda: SimpleNamespace(category_subtree_cache_enabled=True, category_subtree_cache_ttl_seconds=120),
    )
    monkeypatch.setattr(category_service, "get_redis_client", lambda: redis_client)
    monkeypatch.setattr(category_service, "timed_execute_scalars_all", AsyncMock(return_value=[1, 2, 3]))
    monkeypatch.setattr(
        category_service,
        "category_subtree_cache_hits_total",
        SimpleNamespace(add=cache_hits_add),
    )
    monkeypatch.setattr(
        category_service,
        "category_subtree_cache_misses_total",
        SimpleNamespace(add=cache_misses_add),
    )

    subtree_ids = await category_service.get_category_subtree_ids(session, category_id=1)

    assert subtree_ids == [1, 2, 3]
    redis_client.set.assert_awaited_once_with(
        "category_subtree:v1:root:1",
        json.dumps([1, 2, 3]),
        ex=120,
    )
    cache_hits_add.assert_not_called()
    cache_misses_add.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_get_category_subtree_ids_cache_hit_skips_db(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    redis_client = AsyncMock()
    redis_client.get = AsyncMock(side_effect=["3", json.dumps([4, 5])])

    db_fetch = AsyncMock()

    cache_hits_add = MagicMock()
    cache_misses_add = MagicMock()

    monkeypatch.setattr(
        category_service,
        "get_settings",
        lambda: SimpleNamespace(category_subtree_cache_enabled=True, category_subtree_cache_ttl_seconds=120),
    )
    monkeypatch.setattr(category_service, "get_redis_client", lambda: redis_client)
    monkeypatch.setattr(category_service, "timed_execute_scalars_all", db_fetch)
    monkeypatch.setattr(
        category_service,
        "category_subtree_cache_hits_total",
        SimpleNamespace(add=cache_hits_add),
    )
    monkeypatch.setattr(
        category_service,
        "category_subtree_cache_misses_total",
        SimpleNamespace(add=cache_misses_add),
    )

    subtree_ids = await category_service.get_category_subtree_ids(session, category_id=4)

    assert subtree_ids == [4, 5]
    db_fetch.assert_not_awaited()
    cache_hits_add.assert_called_once_with(1)
    cache_misses_add.assert_not_called()


@pytest.mark.asyncio
async def test_get_category_subtree_ids_falls_back_on_redis_error(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    redis_client = AsyncMock()
    redis_client.get = AsyncMock(side_effect=category_service.RedisError("unavailable"))

    cache_hits_add = MagicMock()
    cache_misses_add = MagicMock()

    monkeypatch.setattr(
        category_service,
        "get_settings",
        lambda: SimpleNamespace(category_subtree_cache_enabled=True, category_subtree_cache_ttl_seconds=120),
    )
    monkeypatch.setattr(category_service, "get_redis_client", lambda: redis_client)
    monkeypatch.setattr(category_service, "timed_execute_scalars_all", AsyncMock(return_value=[7]))
    monkeypatch.setattr(
        category_service,
        "category_subtree_cache_hits_total",
        SimpleNamespace(add=cache_hits_add),
    )
    monkeypatch.setattr(
        category_service,
        "category_subtree_cache_misses_total",
        SimpleNamespace(add=cache_misses_add),
    )

    subtree_ids = await category_service.get_category_subtree_ids(session, category_id=7)

    assert subtree_ids == [7]
    cache_hits_add.assert_not_called()
    cache_misses_add.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_invalidate_category_subtree_cache_bumps_version(monkeypatch: pytest.MonkeyPatch):
    redis_client = AsyncMock()
    redis_client.incr = AsyncMock()

    monkeypatch.setattr(
        category_service,
        "get_settings",
        lambda: SimpleNamespace(category_subtree_cache_enabled=True, category_subtree_cache_ttl_seconds=120),
    )
    monkeypatch.setattr(category_service, "get_redis_client", lambda: redis_client)

    await category_service.invalidate_category_subtree_cache()

    redis_client.incr.assert_awaited_once_with("category_subtree_cache_version")
