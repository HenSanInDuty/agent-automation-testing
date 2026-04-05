from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    HUGGINGFACE = "huggingface"
    AZURE = "azure_openai"
    GROQ = "groq"

    @property
    def requires_api_key(self) -> bool:
        """Providers that require an API key."""
        return self in {
            LLMProvider.OPENAI,
            LLMProvider.ANTHROPIC,
            LLMProvider.HUGGINGFACE,
            LLMProvider.AZURE,
            LLMProvider.GROQ,
        }

    @property
    def requires_base_url(self) -> bool:
        """Providers that typically require a base URL."""
        return self in {LLMProvider.OLLAMA, LLMProvider.AZURE}

    @property
    def litellm_prefix(self) -> str:
        """LiteLLM model string prefix for this provider."""
        _map = {
            LLMProvider.OPENAI: "openai",
            LLMProvider.ANTHROPIC: "anthropic",
            LLMProvider.OLLAMA: "ollama",
            LLMProvider.HUGGINGFACE: "huggingface",
            LLMProvider.AZURE: "azure",
            LLMProvider.GROQ: "groq",
        }
        return _map[self]


# ─────────────────────────────────────────────────────────────────────────────
# Base
# ─────────────────────────────────────────────────────────────────────────────


class LLMProfileBase(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Human-readable profile name, e.g. 'GPT-4o Production'",
        examples=["GPT-4o Production"],
    )
    provider: LLMProvider = Field(
        ...,
        description="LLM provider",
        examples=["openai"],
    )
    model: str = Field(
        ...,
        min_length=1,
        max_length=150,
        description="Model identifier, e.g. 'gpt-4o', 'claude-3-5-sonnet-20241022'",
        examples=["gpt-4o"],
    )
    api_key: Optional[str] = Field(
        default=None,
        description="API key for the provider. Stored securely; masked in responses.",
        examples=["sk-..."],
    )
    base_url: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Custom base URL (required for Ollama, Azure, LM Studio, etc.)",
        examples=["http://localhost:11434"],
    )
    temperature: float = Field(
        default=0.1,
        ge=0.0,
        le=2.0,
        description="Sampling temperature. Lower = more deterministic.",
    )
    max_tokens: int = Field(
        default=2048,
        ge=1,
        le=128000,
        description="Maximum number of tokens to generate.",
    )
    is_default: bool = Field(
        default=False,
        description="Whether this profile is the global default for all agents.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Create / Update
# ─────────────────────────────────────────────────────────────────────────────


class LLMProfileCreate(LLMProfileBase):
    """Payload for POST /admin/llm-profiles"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "GPT-4o Production",
                "provider": "openai",
                "model": "gpt-4o",
                "api_key": "sk-...",
                "base_url": None,
                "temperature": 0.1,
                "max_tokens": 2048,
                "is_default": True,
            }
        }
    )


class LLMProfileUpdate(BaseModel):
    """Payload for PUT /admin/llm-profiles/{id} — all fields optional."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    provider: Optional[LLMProvider] = None
    model: Optional[str] = Field(default=None, min_length=1, max_length=150)
    api_key: Optional[str] = None
    base_url: Optional[str] = Field(default=None, max_length=500)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=128000)
    is_default: Optional[bool] = None


# ─────────────────────────────────────────────────────────────────────────────
# Response  (API key always masked)
# ─────────────────────────────────────────────────────────────────────────────


class LLMProfileResponse(BaseModel):
    """Safe response schema — api_key is always masked before sending to the FE.

    The ``id`` field carries the MongoDB ObjectId as a hex string.
    Use :class:`LLMProfileInternal` when the real API key is needed for LLM
    calls — never serialise that class to an HTTP response.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str  # MongoDB ObjectId as hex string
    name: str
    provider: LLMProvider
    model: str
    api_key_masked: Optional[str] = Field(
        default=None,
        alias="api_key",
        description="API key with all but last-4 characters replaced by bullets.",
    )
    base_url: Optional[str]
    temperature: float
    max_tokens: int
    is_default: bool
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _mask_api_key(cls, data: object) -> object:
        """Mask the raw api_key before Pydantic stores it.

        Works both when *data* is a plain ``dict`` and when it is a Beanie
        ``Document`` instance (accessed via ``__dict__`` / ``getattr``).

        For Document objects the attributes are extracted into a plain dict so
        that the aliased field ``api_key_masked`` (alias="api_key") receives
        the masked value rather than the raw key on the document.
        """
        # Beanie Document (or any object with attributes) — extract to dict
        if hasattr(data, "__dict__") and not isinstance(data, dict):
            raw = getattr(data, "api_key", None)
            return {
                "id": str(getattr(data, "id", None) or ""),
                "name": getattr(data, "name", None),
                "provider": getattr(data, "provider", None),
                "model": getattr(data, "model", None),
                "api_key": _mask(raw),
                "base_url": getattr(data, "base_url", None),
                "temperature": getattr(data, "temperature", None),
                "max_tokens": getattr(data, "max_tokens", None),
                "is_default": getattr(data, "is_default", None),
                "created_at": getattr(data, "created_at", None),
                "updated_at": getattr(data, "updated_at", None),
            }

        # Plain dict
        if isinstance(data, dict):
            data = dict(data)  # mutable copy
            data["api_key"] = _mask(data.get("api_key"))
            # Coerce ObjectId to str when coming from a serialised document
            if "id" in data and data["id"] is not None:
                data["id"] = str(data["id"])
            return data

        return data


class LLMProfileInternal(BaseModel):
    """Internal-only schema that exposes the real ``api_key``.

    **Never** serialise this to an HTTP response.  Used exclusively inside
    ``llm_factory.py`` and crew builders where the raw key is needed to
    authenticate against the LLM provider.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str  # MongoDB ObjectId as hex string
    name: str
    provider: LLMProvider
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float
    max_tokens: int
    is_default: bool

    @property
    def litellm_model_string(self) -> str:
        """Return the LiteLLM-style ``'provider/model'`` string."""
        return f"{self.provider.litellm_prefix}/{self.model}"


# ─────────────────────────────────────────────────────────────────────────────
# Test connection payload & response
# ─────────────────────────────────────────────────────────────────────────────


class LLMTestRequest(BaseModel):
    """Optional override payload for POST /admin/llm-profiles/{id}/test"""

    prompt: str = Field(
        default="Reply with the single word: OK",
        description="Test prompt to send to the LLM.",
    )
    timeout_seconds: int = Field(default=15, ge=5, le=60)


class LLMTestResponse(BaseModel):
    success: bool
    message: str
    response_preview: Optional[str] = None
    latency_ms: Optional[int] = None


# ─────────────────────────────────────────────────────────────────────────────
# List response wrapper
# ─────────────────────────────────────────────────────────────────────────────


class LLMProfileListResponse(BaseModel):
    items: list[LLMProfileResponse]
    total: int


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _mask(api_key: Optional[str]) -> Optional[str]:
    """Mask an API key for safe display.

    - ``None`` / empty string → ``None``
    - 8 characters or fewer  → ``"••••••••"``
    - More than 8 characters → ``"••••••••"`` + last 4 characters
    """
    if not api_key:
        return None
    visible = api_key[-4:] if len(api_key) > 8 else ""
    return f"••••••••{visible}"
