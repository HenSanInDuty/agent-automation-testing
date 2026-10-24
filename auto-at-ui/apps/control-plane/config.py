# file cấu hình các thông tin từ env
from functools import lru_cache
from pathlib import PurePosixPath, PureWindowsPath
from uuid import UUID

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables and an optional `.env` file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Auto-AT Control Plane"
    environment: str = "local"
    log_level: str = "INFO"
    json_logging_enabled: bool = True
    log_service_name: str = "auto-at-control-plane"
    auth_mode: str = "local"
    session_cookie_name: str = "auto_at_session"
    csrf_cookie_name: str = "auto_at_csrf"
    session_ttl_seconds: int = Field(default=28_800, ge=300, le=2_592_000)
    auth_login_max_attempts: int = Field(default=5, ge=1, le=100)
    auth_login_window_seconds: int = Field(default=60, ge=1, le=3_600)
    dashboard_cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    port: int = Field(default=7000, ge=1, le=65535)
    ollama_model: str = "ollama:devstral-2"
    ollama_base_url: str = "http://127.0.0.1:11434"
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    huggingface_api_key: str | None = None
    gemini_api_key: str | None = Field(default=None, repr=False, exclude=True)
    huggingface_base_url: str = "https://router.huggingface.co/v1"
    agent_provider: str = "huggingface"
    agent_model: str = "Qwen/Qwen2.5-Coder-32B-Instruct"
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
    agent_generation_prompt_version: str = "test-generation-v5"
    agent_generation_redaction_policy_version: str = "generation-redaction-v1"
    vision_enabled: bool = False
    vision_trace_v4_enabled: bool = False
    codex_bridge_enabled: bool = False
    codex_bridge_id: UUID | None = None
    codex_bridge_allowed_tenant: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,200}$")
    codex_bridge_host_spool: str | None = None
    codex_bridge_container_spool: str = "/codex-jobs"
    codex_bridge_executable: str | None = None
    codex_bridge_heartbeat_seconds: float = Field(default=2, gt=0, le=2)
    codex_bridge_stale_seconds: float = Field(default=10, ge=3, le=10)
    codex_bridge_cancel_poll_seconds: float = Field(default=1, gt=0, le=2)
    codex_bridge_kill_grace_seconds: float = Field(default=3, gt=0, le=3)
    codex_bridge_max_pending: int = Field(default=10, ge=1, le=10)
    vision_provider: str = "huggingface"
    vision_model: str = "Qwen/Qwen3.8-27B:deepinfra"
    vision_raw_screenshot_transfer_accepted: bool = False
    vision_raw_screenshot_transfer_provider: str | None = None
    vision_max_steps: int = Field(default=3, ge=1, le=10)
    vision_max_screenshot_bytes: int = Field(default=1_000_000, ge=1_024, le=5_000_000)
    vision_max_session_seconds: int = Field(default=120, ge=1, le=3_600)
    vision_max_cost_usd: float = Field(default=0.25, gt=0, le=1_000)
    vision_max_requests_per_minute: int = Field(default=5, ge=1, le=10_000)
    # Fernet key supplied only through environment/secret configuration.  Vision
    # submission remains unavailable when an enabled tenant has not configured it.
    vision_intent_encryption_key: str | None = None
    vision_intent_retention_days: int = Field(default=60, ge=1, le=60)
    # Separate deployment-secret namespace for privileged diagnostic evidence.
    vision_debug_evidence_encryption_key: str | None = None
    vision_debug_evidence_key_id: str | None = None
    vision_debug_evidence_previous_encryption_key: str | None = None
    vision_debug_evidence_previous_key_id: str | None = None
    vision_debug_evidence_retention_days: int = Field(default=7, ge=7, le=7)
    vision_debug_evidence_max_payload_bytes: int = Field(default=16_384, ge=1_024, le=16_384)
    vision_debug_evidence_cleanup_interval_seconds: int = Field(default=3_600, ge=60, le=86_400)
    vision_debug_evidence_cleanup_batch_size: int = Field(default=100, ge=1, le=1_000)
    vision_worker_secret: str | None = None
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    supabase_vision_bucket: str = "vision-transient"
    google_drive_service_account_file: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE", "GOOGLE_APPLICATION_CREDENTIALS"
        ),
    )
    google_drive_oauth_client_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_DRIVE_OAUTH_CLIENT_ID", "GOOGLE_CLIENT_ID"),
    )
    google_drive_oauth_client_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_DRIVE_OAUTH_CLIENT_SECRET", "GOOGLE_CLIENT_SECRET"),
    )
    google_drive_oauth_refresh_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_DRIVE_OAUTH_REFRESH_TOKEN", "GOOGLE_REFRESH_TOKEN"),
    )
    google_drive_vision_folder_id: str | None = None
    google_drive_vision_delete_after_delivery: bool = False
    vision_temporary_url_ttl_seconds: int = Field(default=60, ge=1, le=60)
    agent_reporting_prompt_version: str = "run-review-v2"
    database_url: str = "postgresql://auto_at:local-development-only@127.0.0.1:5432/auto_at"
    redis_url: str = "redis://127.0.0.1:6379/0"
    rustfs_endpoint: str = "http://127.0.0.1:9000"
    rustfs_access_key: str = "rustfsadmin"
    rustfs_secret_key: str = "rustfsadmin"
    rustfs_bucket: str = "auto-at-artifacts"
    rustfs_secure: bool = False
    rustfs_region: str = "us-east-1"
    rustfs_path_style: bool = True
    artifact_upload_max_bytes: int = Field(default=100_000_000, ge=1_024, le=1_000_000_000)
    runner_dispatch_enabled: bool = False
    playwright_worker_url: str = "http://127.0.0.1:7100"
    worker_progress_callback_secret: str | None = None
    # Staging-only shared volume used between the worker and workflow promoter.
    artifact_root: str = "/tmp/auto-at-artifacts"
    temporal_enabled: bool = False
    temporal_address: str = "127.0.0.1:7233"
    temporal_namespace: str = "auto-at-local"
    temporal_task_queue: str = "auto-at-run-dispatch-v1"
    temporal_outbox_poll_interval_seconds: float = Field(default=1.0, ge=0.1, le=60.0)
    artifact_retention_cleanup_interval_seconds: int = Field(default=3_600, ge=60, le=86_400)
    temporal_activity_timeout_seconds: int = Field(default=600, ge=1, le=3_600)
    temporal_run_deadline_seconds: int = Field(default=1_200, ge=1, le=7_200)
    temporal_retry_initial_interval_seconds: int = Field(default=1, ge=1, le=300)
    temporal_retry_maximum_interval_seconds: int = Field(default=30, ge=1, le=600)
    temporal_retry_maximum_attempts: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def validate_codex_bridge(self) -> "Settings":
        for value in (self.codex_bridge_host_spool, self.codex_bridge_container_spool,
                      self.codex_bridge_executable):
            if value is None:
                continue
            windows, posix = PureWindowsPath(value), PurePosixPath(value)
            if (not (windows.is_absolute() or posix.is_absolute())
                    or ".." in windows.parts or ".." in posix.parts
                    or any(ord(c) < 32 for c in value) or '"' in value
                    or value.startswith(("\\\\", "//"))):
                raise ValueError("Codex paths must be absolute local paths without traversal")
        executable = self.codex_bridge_executable
        if executable and PureWindowsPath(executable).name.lower() not in {"codex.exe", "codex"}:
            raise ValueError("Codex requires a fixed native executable, not a shell or shim")
        if self.codex_bridge_enabled and (
            self.environment != "local" or not self.codex_bridge_id
            or not self.codex_bridge_allowed_tenant or not self.codex_bridge_host_spool
            or not executable
        ):
            raise ValueError("enabled Codex bridge requires explicit local tenant, ID and paths")
        if self.codex_bridge_stale_seconds <= self.codex_bridge_heartbeat_seconds:
            raise ValueError("bridge stale limit must exceed heartbeat interval")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
