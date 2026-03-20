"""Application configuration loaded from environment variables.

This module centralizes runtime settings for database, API, and observability
concerns. Values are read from `.env` (when present) and can be overridden via
environment variables.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings with sane defaults for local development.

    The class inherits from `BaseSettings`, so each field can be overridden by
    environment variables following pydantic-settings conventions.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/commerce_demo"
    database_pool_size: int = 20
    database_max_overflow: int = 5
    database_pool_timeout: int = 5
    database_pool_pre_ping: bool = False
    database_pool_recycle: int = 1800
    api_prefix: str = "/api/v1"
    auto_create_schema: bool = True
    default_limit: int = 20
    max_limit: int = 100
    telemetry_enabled: bool = True
    otel_service_name: str = "commerce-system-demo"
    otel_environment: str = "dev"
    otel_resource_attributes: str = ""
    otel_exporter_otlp_endpoint: str | None = None
    otel_exporter_otlp_insecure: bool = True
    otel_metrics_enabled: bool = True
    otel_metrics_path: str = "/metrics"
    otel_trace_excluded_urls: str = ""
    log_level: str = "INFO"
    health_check_db_retries: int = 3
    health_check_db_timeout: float = 2.0


@lru_cache
def get_settings() -> Settings:
    """Return a cached `Settings` instance for the process lifetime.

    Caching prevents repeated environment parsing across imports and request
    handling code.
    """

    return Settings()
