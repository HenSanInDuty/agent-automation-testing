# file cấu hình các thông tin từ env
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables and an optional `.env` file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Auto-AT Control Plane"
    environment: str = "local"
    auth_mode: str = "local"
    port: int = Field(default=7000, ge=1, le=65535)
    ollama_model: str = "ollama:devstral-2"
    ollama_base_url: str = "http://127.0.0.1:11434"
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    agent_provider: str = "openrouter"
    agent_model: str = "openai/gpt-5-mini"
    agent_fallback_enabled: bool = False
    agent_fallback_provider: str | None = None
    agent_fallback_model: str | None = None
    agent_evidence_metadata_enabled: bool = True
    agent_evidence_redacted_text_enabled: bool = True
    agent_evidence_screenshots_enabled: bool = False
    agent_step_max_tokens: int = Field(default=8_000, ge=1, le=100_000)
    agent_max_steps_per_run: int = Field(default=2, ge=1, le=10)
    agent_max_evidence_bytes_per_step: int = Field(default=250_000, ge=1_024, le=5_000_000)
    agent_max_concurrency: int = Field(default=1, ge=1, le=100)
    agent_generation_max_tokens: int = Field(default=4_000, ge=1, le=100_000)
    agent_generation_max_concurrency: int = Field(default=1, ge=1, le=100)
    agent_generation_max_requests_per_minute: int = Field(default=10, ge=1, le=10_000)
    agent_generation_max_cost_usd: float = Field(default=1.0, gt=0, le=1_000)
    agent_generation_prompt_version: str = "test-generation-v1"
    agent_generation_redaction_policy_version: str = "generation-redaction-v1"
    database_url: str = "postgresql://auto_at:local-development-only@127.0.0.1:5432/auto_at"
    redis_url: str = "redis://127.0.0.1:6379/0"
    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "auto-at-artifacts"
    minio_secure: bool = False
    runner_dispatch_enabled: bool = False
    playwright_worker_url: str = "http://127.0.0.1:7100"
    artifact_root: str = "/tmp/auto-at-artifacts"
    temporal_enabled: bool = False
    temporal_address: str = "127.0.0.1:7233"
    temporal_namespace: str = "auto-at-local"
    temporal_task_queue: str = "auto-at-run-dispatch-v1"
    temporal_outbox_poll_interval_seconds: float = Field(default=1.0, ge=0.1, le=60.0)
    temporal_activity_timeout_seconds: int = Field(default=600, ge=1, le=3_600)
    temporal_run_deadline_seconds: int = Field(default=1_200, ge=1, le=7_200)
    temporal_retry_initial_interval_seconds: int = Field(default=1, ge=1, le=300)
    temporal_retry_maximum_interval_seconds: int = Field(default=30, ge=1, le=600)
    temporal_retry_maximum_attempts: int = Field(default=3, ge=1, le=10)


@lru_cache
def get_settings() -> Settings:
    return Settings()
