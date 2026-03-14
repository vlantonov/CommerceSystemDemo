"""Database engine, session factory, and schema lifecycle helpers."""

from collections.abc import AsyncGenerator

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
    """Get engine."""
    if _engine is None:
        initialize_database()
    assert _engine is not None
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get session factory."""
    if _session_factory is None:
        initialize_database()
    assert _session_factory is not None
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get session."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session


async def create_schema() -> None:
    # Import models so SQLAlchemy metadata is fully populated before create_all.
    """Create schema."""
    import app.models  # noqa: F401

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_schema() -> None:
    """Drop schema."""
    import app.models  # noqa: F401

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
