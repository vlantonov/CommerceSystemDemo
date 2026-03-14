from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates

from app.api import api_router
from app.core.config import get_settings
from app.db.session import create_schema, get_engine, initialize_database
from app.observability import (
    ObservabilityRoute,
    initialize_app_observability,
    initialize_database_observability,
    start_log_listener,
    stop_log_listener,
)

logger = logging.getLogger("app.lifecycle")
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    start_log_listener()
    settings = get_settings()
    initialize_database(settings.database_url)
    initialize_database_observability(get_engine(), settings)
    logger.info("application_startup", extra={"database_initialized": True})

    if settings.auto_create_schema:
        await create_schema()
        logger.info("database_schema_created")

    yield

    logger.info("application_shutdown")
    stop_log_listener()


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

    @app.get("/", tags=["home"])
    async def home(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"project_name": "Commerce System Demo"},
        )

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
