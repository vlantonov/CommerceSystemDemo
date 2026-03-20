"""Unit tests for category service helper functions."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import category_service


@pytest.mark.asyncio
async def test_category_depth_stops_when_parent_missing(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()

    async def fake_timed_get(_session, _model, category_id):
        if category_id == 1:
            return SimpleNamespace(parent_id=2)
        return None

    monkeypatch.setattr(category_service, "timed_get", fake_timed_get)

    depth = await category_service.category_depth(session, parent_id=1)
    assert depth == 2


@pytest.mark.asyncio
async def test_validate_no_cycles_raises_for_cycle(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()

    async def fake_timed_get(_session, _model, category_id):
        if category_id == 2:
            return SimpleNamespace(parent_id=1)
        return None

    monkeypatch.setattr(category_service, "timed_get", fake_timed_get)

    with pytest.raises(ValueError, match="Category cycle detected"):
        await category_service.validate_no_cycles(session, category_id=1, new_parent_id=2)


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

    with pytest.raises(category_service.CategoryDepthError):
        await category_service.validate_category_reparent(session, category_id=1, new_parent_id=2)


@pytest.mark.asyncio
async def test_category_depth_returns_when_exceeding_max(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()

    async def fake_timed_get(_session, _model, category_id):
        return SimpleNamespace(parent_id=category_id + 1)

    monkeypatch.setattr(category_service, "timed_get", fake_timed_get)

    depth = await category_service.category_depth(session, parent_id=1)
    assert depth == category_service.MAX_CATEGORY_DEPTH + 1


@pytest.mark.asyncio
async def test_validate_no_cycles_breaks_on_missing_candidate(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()
    monkeypatch.setattr(category_service, "timed_get", AsyncMock(return_value=None))

    await category_service.validate_no_cycles(session, category_id=1, new_parent_id=2)