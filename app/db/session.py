"""Database engine, session factory, and schema lifecycle helpers.

The primary path for HTTP handlers uses FastAPI's dependency injection:
``get_session`` reads from ``request.app.state.session_factory``, which
is populated during the application lifespan.

Module-level helpers (``initialize_database``, ``get_engine``,
``get_session_factory``) are retained for use in tests, CLI scripts, and
the Alembic migration runner — contexts where no ``Request`` is available.
"""

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.db.base import Base

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_active_database_url: str | None = None


def initialize_database(database_url: str | None = None, force: bool = False) -> None:
    """Initialize database."""
    global _engine, _session_factory, _active_database_url

    url = database_url or get_settings().database_url
    if _engine is not None and _active_database_url == url and not force:
        return

    settings = get_settings()
    _engine = create_async_engine(
        url,
        future=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout,
        pool_pre_ping=settings.database_pool_pre_ping,
        pool_recycle=settings.database_pool_recycle,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False, autoflush=False)
    _active_database_url = url


def get_engine() -> AsyncEngine:
    """Return the module-level engine (for tests and scripts)."""
    if _engine is None:
        initialize_database()
    assert _engine is not None
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the module-level session factory (for tests and scripts)."""
    if _session_factory is None:
        initialize_database()
    assert _session_factory is not None
    return _session_factory


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a DB session from ``app.state``."""
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session


async def create_schema(engine: AsyncEngine | None = None) -> None:
    """Create schema."""
    import app.models  # noqa: F401

    engine = engine or get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_schema(engine: AsyncEngine | None = None) -> None:
    """Drop schema."""
    import app.models  # noqa: F401

    engine = engine or get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
