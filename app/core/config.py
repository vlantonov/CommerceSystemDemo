from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/commerce_demo"
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
