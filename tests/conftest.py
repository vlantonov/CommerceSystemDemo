"""Shared pytest fixtures for integration and database tests."""

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from testcontainers.postgres import PostgresContainer

from app.core.config import get_settings
from app.db.session import create_schema, drop_schema, get_session_factory, initialize_database


@pytest.fixture(scope="session")
def postgres_url() -> str:
    """Handle postgres url."""
    with PostgresContainer("postgres:16-alpine") as container:
        sync_url = container.get_connection_url()
        async_url = sync_url.replace("postgresql+psycopg2", "postgresql+asyncpg")
        yield async_url


@pytest.fixture(scope="session", autouse=True)
def configure_database(postgres_url: str) -> None:
    """Configure database."""
    os.environ["DATABASE_URL"] = postgres_url
    get_settings.cache_clear()
    initialize_database(postgres_url, force=True)


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncIterator[AsyncSession]:
    """Handle db session."""
    await drop_schema()
    await create_schema()

    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session
