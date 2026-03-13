from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from app.api import api_router
from app.core.config import get_settings
from app.db.session import create_schema, get_engine, initialize_database
from app.observability import (
    ObservabilityRoute,
    initialize_app_observability,
    initialize_database_observability,
)

logger = logging.getLogger("app.lifecycle")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    initialize_database(settings.database_url)
    initialize_database_observability(get_engine(), settings)
    logger.info("application_startup", extra={"database_initialized": True})

    if settings.auto_create_schema:
        await create_schema()
        logger.info("database_schema_created")

    yield

    logger.info("application_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Commerce System Demo",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.router.route_class = ObservabilityRoute
    initialize_app_observability(app, settings)
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
