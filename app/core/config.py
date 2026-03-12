from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/commerce_demo"
    api_prefix: str = "/api/v1"
    auto_create_schema: bool = True
    default_limit: int = 20
    max_limit: int = 100


@lru_cache
def get_settings() -> Settings:
    return Settings()
