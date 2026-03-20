"""FastAPI application factory and lifecycle setup."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from jinja2 import TemplateNotFound

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


def _resolve_template_directories() -> list[str]:
    """Return existing template directories for source and packaged layouts."""
    app_dir = Path(__file__).resolve().parent
    candidates = [
        app_dir.parent / "templates",  # repository layout: <root>/templates
        app_dir / "templates",  # packaged layout:
        # <site-packages>/app/templates
        Path.cwd() / "templates",  # runtime cwd layout (common in PaaS)
    ]

    directories: list[str] = []
    for candidate in candidates:
        if candidate.is_dir():
            resolved = str(candidate.resolve())
            if resolved not in directories:
                directories.append(resolved)

    if directories:
        return directories

    # Last-resort default keeps startup deterministic; missing template is
    # handled gracefully in the route fallback below.
    return [str((app_dir.parent / "templates").resolve())]


templates = Jinja2Templates(directory=_resolve_template_directories())


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown tasks."""
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
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Commerce System Demo",
        version="0.1.3",
        lifespan=lifespan,
    )
    app.router.route_class = ObservabilityRoute
    initialize_app_observability(app, settings)
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/", tags=["home"])
    async def home(request: Request):
        try:
            return templates.TemplateResponse(
                request=request,
                name="index.html",
                context={"project_name": "Commerce System Demo"},
            )
        except TemplateNotFound:
            logger.exception("home_template_missing")
            return HTMLResponse(
                content=(
                    "<!doctype html><html><head>"
                    "<title>Commerce System Demo</title>"
                    "<meta charset='utf-8'>"
                    "<meta name='viewport' "
                    "content='width=device-width, initial-scale=1'>"
                    "</head><body>"
                    "<h1>Commerce System Demo</h1>"
                    "<p>"
                    "Template not available in this deployment. Use API docs:"
                    "</p>"
                    "<ul><li><a href='/docs'>/docs</a></li>"
                    "<li><a href='/redoc'>/redoc</a></li>"
                    "<li><a href='/health'>/health</a></li></ul>"
                    "</body></html>"
                ),
                status_code=200,
            )

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        import asyncio
        import time

        from sqlalchemy import text

        from app.db.session import get_engine
        from app.observability.metrics import health_check_duration_seconds, health_check_total

        settings = get_settings()
        retries = settings.health_check_db_retries
        timeout = settings.health_check_db_timeout
        engine = get_engine()
        start = time.monotonic()
        last_error: Exception | None = None

        for attempt in range(1, retries + 1):
            try:
                async with asyncio.timeout(timeout):
                    async with engine.connect() as conn:
                        await conn.execute(text("SELECT 1"))
                duration = time.monotonic() - start
                health_check_total.add(1, {"status": "ok"})
                health_check_duration_seconds.record(duration, {"status": "ok"})
                return {"status": "ok", "database": "available"}
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "health_check_db_attempt_failed",
                    extra={"attempt": attempt, "max_retries": retries, "error": str(exc)},
                )
                if attempt < retries:
                    await asyncio.sleep(0.1 * attempt)

        duration = time.monotonic() - start
        health_check_total.add(1, {"status": "error"})
        health_check_duration_seconds.record(duration, {"status": "error"})
        logger.error(
            "health_check_database_failure",
            extra={"retries_exhausted": retries, "error": str(last_error)},
        )
        return JSONResponse(
            status_code=503,
            content={"status": "error", "database": "unavailable"},
        )

    return app


app = create_app()
