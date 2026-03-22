"""Unit tests for category service helper functions."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

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
    monkeypatch.setattr(category_service, "get_category_or_none", AsyncMock(return_value=None))

    with pytest.raises(category_service.CategoryParentNotFoundError):
        await category_service.validate_category_parent(session, parent_id=99)


@pytest.mark.asyncio
async def test_validate_category_parent_raises_depth_error(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    monkeypatch.setattr(
        category_service,
        "get_category_or_none",
        AsyncMock(return_value=SimpleNamespace(id=1, parent_id=None)),
    )
    monkeypatch.setattr(
        category_service,
        "category_depth",
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
    monkeypatch.setattr(category_service, "get_category_or_none", AsyncMock(return_value=None))

    with pytest.raises(category_service.CategoryParentNotFoundError):
        await category_service.validate_category_reparent(session, category_id=1, new_parent_id=77)


@pytest.mark.asyncio
async def test_validate_category_reparent_raises_cycle_error(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    monkeypatch.setattr(
        category_service,
        "get_category_or_none",
        AsyncMock(return_value=SimpleNamespace(id=2, parent_id=None)),
    )
    monkeypatch.setattr(
        category_service,
        "validate_no_cycles",
        AsyncMock(side_effect=ValueError("Category cycle detected")),
    )

    with pytest.raises(category_service.CategoryCycleError, match="Category cycle detected"):
        await category_service.validate_category_reparent(session, category_id=1, new_parent_id=2)


@pytest.mark.asyncio
async def test_validate_category_reparent_raises_depth_error(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    monkeypatch.setattr(
        category_service,
        "get_category_or_none",
        AsyncMock(return_value=SimpleNamespace(id=2, parent_id=None)),
    )
    monkeypatch.setattr(category_service, "validate_no_cycles", AsyncMock(return_value=None))
    monkeypatch.setattr(
        category_service,
        "category_depth",
        AsyncMock(return_value=category_service.MAX_CATEGORY_DEPTH),
    )
    monkeypatch.setattr(
        category_service,
        "category_subtree_height",
        AsyncMock(return_value=1),
    )

    with pytest.raises(category_service.CategoryDepthError):
        await category_service.validate_category_reparent(session, category_id=1, new_parent_id=2)


@pytest.mark.asyncio
async def test_validate_category_reparent_raises_depth_error_for_deep_subtree(monkeypatch: pytest.MonkeyPatch):
    """Moving a category with a deep subtree under a parent should fail if combined depth exceeds limit."""
    session = AsyncMock()
    monkeypatch.setattr(
        category_service,
        "get_category_or_none",
        AsyncMock(return_value=SimpleNamespace(id=2, parent_id=None)),
    )
    monkeypatch.setattr(category_service, "validate_no_cycles", AsyncMock(return_value=None))
    # Parent depth alone is fine (90 < 100), but subtree adds 15 → 90 + 15 = 105 > 100
    monkeypatch.setattr(
        category_service,
        "category_depth",
        AsyncMock(return_value=90),
    )
    monkeypatch.setattr(
        category_service,
        "category_subtree_height",
        AsyncMock(return_value=15),
    )

    with pytest.raises(category_service.CategoryDepthError):
        await category_service.validate_category_reparent(session, category_id=1, new_parent_id=2)


@pytest.mark.asyncio
async def test_validate_category_reparent_allows_when_combined_depth_fits(monkeypatch: pytest.MonkeyPatch):
    """Moving a category succeeds when parent depth + subtree height fits within limit."""
    session = AsyncMock()
    monkeypatch.setattr(
        category_service,
        "get_category_or_none",
        AsyncMock(return_value=SimpleNamespace(id=2, parent_id=None)),
    )
    monkeypatch.setattr(category_service, "validate_no_cycles", AsyncMock(return_value=None))
    # Parent depth 90, subtree height 10 → 90 + 10 = 100 <= 100 → OK
    monkeypatch.setattr(
        category_service,
        "category_depth",
        AsyncMock(return_value=90),
    )
    monkeypatch.setattr(
        category_service,
        "category_subtree_height",
        AsyncMock(return_value=10),
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
