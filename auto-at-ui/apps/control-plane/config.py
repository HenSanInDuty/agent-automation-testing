# file cấu hình các thông tin từ env
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables and an optional `.env` file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Auto-AT Control Plane"
    environment: str = "local"
    port: int = Field(default=7000, ge=1, le=65535)
    ollama_model: str = "ollama:devstral-2"
    ollama_base_url: str = "http://127.0.0.1:11434"
    database_url: str = "postgresql://auto_at:local-development-only@127.0.0.1:5432/auto_at"
    redis_url: str = "redis://127.0.0.1:6379/0"
    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "auto-at-artifacts"
    minio_secure: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
