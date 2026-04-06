from functools import lru_cache
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables and/or a ``.env`` file.

    All fields can be overridden by setting the corresponding environment variable
    (case-insensitive).  Pydantic-Settings handles coercion automatically, so
    ``APP_PORT=9000`` in the environment yields an ``int`` here.

    The ``@lru_cache`` on :func:`get_settings` ensures that only one
    ``Settings`` instance is ever created per process lifetime.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ───────────────────────────────────────────────────────
    APP_ENV: str = "development"
    APP_PORT: int = 8000
    APP_HOST: str = "0.0.0.0"
    APP_TITLE: str = "Auto-AT API"
    APP_VERSION: str = "3.0.0"
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:3001"

    # ── Database (V2 — MongoDB) ───────────────────────────────────
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "auto_at"

    # ── Default LLM fallback (khi không có profile nào is_default=True) ──
    DEFAULT_LLM_PROVIDER: str = "openai"
    DEFAULT_LLM_MODEL: str = "gpt-4o"
    DEFAULT_LLM_API_KEY: Optional[str] = None
    DEFAULT_LLM_BASE_URL: Optional[str] = None
    DEFAULT_LLM_TEMPERATURE: float = 0.1
    DEFAULT_LLM_MAX_TOKENS: int = 2048

    # ── File upload ───────────────────────────────────────────────
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE_MB: int = 50

    # ── Security ──────────────────────────────────────────────────
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    ENCRYPT_API_KEYS: bool = False  # set True in production

    # ── Seed ─────────────────────────────────────────────────────
    AUTO_SEED: bool = True  # tự động seed DB khi khởi động

    # ── Crew / Pipeline ───────────────────────────────────────────
    # When True, all crews produce deterministic mock output without calling any LLM.
    # Useful for development on Windows (no crewai wheels) and CI pipelines.
    MOCK_CREWS: bool = False

    # Maximum number of concurrent pipeline runs allowed
    MAX_CONCURRENT_RUNS: int = 3

    # Per-stage timeout in seconds (0 = no timeout)
    INGESTION_TIMEOUT_SECONDS: int = 120
    TESTCASE_TIMEOUT_SECONDS: int = 600
    EXECUTION_TIMEOUT_SECONDS: int = 300
    REPORTING_TIMEOUT_SECONDS: int = 180

    # Pause timeout — auto-cancel if pipeline stays paused longer than this
    PAUSE_TIMEOUT_SECONDS: int = 3600  # 1 hour

    # Chunk settings for ingestion
    INGESTION_CHUNK_SIZE: int = 2000
    INGESTION_CHUNK_OVERLAP: int = 200

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, v: str) -> str:
        """Strip leading/trailing whitespace from the raw origins string."""
        return v.strip()

    @property
    def allowed_origins_list(self) -> list[str]:
        """Split the comma-separated ``ALLOWED_ORIGINS`` string into a list."""
        return [
            origin.strip()
            for origin in self.ALLOWED_ORIGINS.split(",")
            if origin.strip()
        ]

    @property
    def is_development(self) -> bool:
        """Return ``True`` when ``APP_ENV`` is ``"development"``."""
        return self.APP_ENV.lower() == "development"

    @property
    def is_production(self) -> bool:
        """Return ``True`` when ``APP_ENV`` is ``"production"``."""
        return self.APP_ENV.lower() == "production"

    @property
    def max_file_size_bytes(self) -> int:
        """Convert :attr:`MAX_FILE_SIZE_MB` to bytes."""
        return self.MAX_FILE_SIZE_MB * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Return the cached :class:`Settings` singleton.

    Using ``@lru_cache`` means the ``.env`` file (and environment) is read
    exactly once per process, making repeated calls essentially free.
    """
    return Settings()


# Module-level singleton — import this throughout the application:
#   from app.config import settings
settings: Settings = get_settings()
