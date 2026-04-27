from __future__ import annotations

"""
core/llm_factory.py
───────────────────
Builds CrewAI-compatible LLM objects from LLMProfile DB records via LiteLLM.

LiteLLM model string format:  "<provider>/<model>"
Examples:
    openai/gpt-4o
    anthropic/claude-3-5-sonnet-20241022
    ollama/llama3
    azure/gpt-4o
    groq/llama-3.1-70b-versatile
    huggingface/ibm-granite/granite-3.0-2b-instruct

Usage:
    from app.core.llm_factory import build_llm, build_fallback_llm
    from app.db.models import LLMProfile

    llm = build_llm(profile)          # from DB profile ORM object
    llm = build_fallback_llm()        # from environment variables
"""

import logging
import time
from typing import TYPE_CHECKING, Optional

from app.config import settings

if TYPE_CHECKING:
    from app.db.models import LLMProfileDocument
    from app.schemas.llm_profile import LLMProfileInternal

logger = logging.getLogger(__name__)

# ── Optional crewai import ────────────────────────────────────────────────────
# crewai requires lancedb which has no Windows wheels on PyPI (as of 1.x).
# We import it at module level so tests can patch `app.core.llm_factory.LLM`
# without crewai being physically installed.  build_llm() raises ImportError
# at *call time* when LLM is None, keeping the rest of the module importable.
try:
    from crewai import LLM  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    LLM = None  # type: ignore[assignment,misc]

try:
    import litellm  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    litellm = None  # type: ignore[assignment]

# ─────────────────────────────────────────────────────────────────────────────
# Provider → LiteLLM prefix mapping
# ─────────────────────────────────────────────────────────────────────────────

_PROVIDER_PREFIX: dict[str, str] = {
    "openai": "openai",
    "anthropic": "anthropic",
    "ollama": "ollama",
    "huggingface": "huggingface",
    "azure_openai": "azure",
    "groq": "groq",
    "lm_studio": "openai",  # LM Studio exposes an OpenAI-compatible endpoint
}

# Providers that work without an API key (local inference)
_NO_KEY_PROVIDERS = {"ollama", "lm_studio"}

# Default model suggestions per provider (used in validation messages)
_PROVIDER_DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o",
    "anthropic": "claude-3-5-sonnet-20241022",
    "ollama": "llama3",
    "huggingface": "ibm-granite/granite-3.0-2b-instruct",
    "azure_openai": "gpt-4o",
    "groq": "llama-3.1-70b-versatile",
}


# ─────────────────────────────────────────────────────────────────────────────
# Public helpers
# ─────────────────────────────────────────────────────────────────────────────


def get_model_string(provider: str, model: str) -> str:
    """
    Build the LiteLLM-style 'provider/model' string.

    Args:
        provider: One of the keys in _PROVIDER_PREFIX.
        model:    The raw model name (e.g. 'gpt-4o').

    Returns:
        LiteLLM model string, e.g. 'openai/gpt-4o'.

    Raises:
        ValueError: If the provider is not recognised.
    """
    prefix = _PROVIDER_PREFIX.get(provider)
    if prefix is None:
        supported = sorted(_PROVIDER_PREFIX.keys())
        raise ValueError(
            f"Unsupported LLM provider {provider!r}. Supported providers: {supported}"
        )
    return f"{prefix}/{model}"


def build_llm(profile: "LLMProfileDocument | LLMProfileInternal"):
    """
    Build a CrewAI LLM object from a DB profile (ORM instance or
    LLMProfileInternal Pydantic schema).

    The returned object is a ``crewai.LLM`` instance backed by LiteLLM,
    which supports 100+ providers transparently.

    Args:
        profile: An ORM ``LLMProfile`` or a ``LLMProfileInternal`` schema.
                 Must have the real (unmasked) api_key.

    Returns:
        crewai.LLM instance ready to be passed to a CrewAI Agent.

    Raises:
        ValueError: If the provider is unsupported.
        ImportError: If crewai is not installed.
    """
    if LLM is None:
        raise ImportError(
            "crewai is not installed. "
            "On Linux/macOS run: uv add crewai  "
            "On Windows use Docker/WSL2 for Phase 2+ crew execution."
        )

    provider = str(profile.provider)
    model = str(profile.model)
    model_string = get_model_string(provider, model)

    kwargs: dict = {
        "model": model_string,
        "temperature": float(profile.temperature),
        "max_tokens": int(profile.max_tokens),
    }

    # API key — skip for local providers (e.g. Ollama)
    api_key = getattr(profile, "api_key", None)
    if api_key and provider not in _NO_KEY_PROVIDERS:
        kwargs["api_key"] = api_key
    elif provider not in _NO_KEY_PROVIDERS and not api_key:
        logger.warning(
            "LLM profile '%s' has no api_key set for provider '%s'. "
            "Calls will likely fail unless the key is set via environment variable.",
            getattr(profile, "name", "unknown"),
            provider,
        )

    # Base URL — required for Ollama, Azure, LM Studio, vLLM, etc.
    base_url = getattr(profile, "base_url", None)
    if base_url:
        kwargs["base_url"] = base_url
    elif provider == "ollama":
        kwargs["base_url"] = settings.OLLAMA_BASE_URL
        logger.debug("Ollama base_url not set — using: %s", settings.OLLAMA_BASE_URL)

    logger.debug(
        "Building LLM: model=%s temperature=%.2f max_tokens=%d",
        model_string,
        kwargs["temperature"],
        kwargs["max_tokens"],
    )

    return LLM(**kwargs)


def build_fallback_llm():
    """
    Build a LLM from environment variables when no DB profile is available.
    Uses the DEFAULT_LLM_* settings defined in config.py.

    Returns:
        crewai.LLM instance.
    """
    if LLM is None:
        raise ImportError(
            "crewai is not installed. "
            "On Linux/macOS run: uv add crewai  "
            "On Windows use Docker/WSL2 for Phase 2+ crew execution."
        )

    provider = settings.DEFAULT_LLM_PROVIDER
    model = settings.DEFAULT_LLM_MODEL
    model_string = get_model_string(provider, model)

    kwargs: dict = {
        "model": model_string,
        "temperature": settings.DEFAULT_LLM_TEMPERATURE,
        "max_tokens": settings.DEFAULT_LLM_MAX_TOKENS,
    }

    if settings.DEFAULT_LLM_API_KEY:
        kwargs["api_key"] = settings.DEFAULT_LLM_API_KEY

    if settings.DEFAULT_LLM_BASE_URL:
        kwargs["base_url"] = settings.DEFAULT_LLM_BASE_URL
    elif provider == "ollama":
        kwargs["base_url"] = settings.OLLAMA_BASE_URL

    logger.info(
        "Using fallback LLM from environment: %s (temp=%.2f)",
        model_string,
        kwargs["temperature"],
    )

    return LLM(**kwargs)


def resolve_llm(
    agent_profile: Optional["LLMProfileDocument | LLMProfileInternal"],
    default_profile: Optional["LLMProfileDocument | LLMProfileInternal"],
):
    """
    Resolve the correct LLM for an agent following the override hierarchy:

        agent-level profile  →  global default profile  →  env var fallback

    Args:
        agent_profile:   The LLM profile assigned to a specific agent, or None.
        default_profile: The global default LLM profile from the DB, or None.

    Returns:
        crewai.LLM instance.
    """
    if agent_profile is not None:
        logger.debug(
            "Using agent-level LLM profile: %s",
            getattr(agent_profile, "name", "unknown"),
        )
        return build_llm(agent_profile)

    if default_profile is not None:
        logger.debug(
            "Using global default LLM profile: %s",
            getattr(default_profile, "name", "unknown"),
        )
        return build_llm(default_profile)

    logger.debug("No DB profile found — falling back to environment variables.")
    return build_fallback_llm()


# ─────────────────────────────────────────────────────────────────────────────
# Connection test helper (used by /admin/llm-profiles/{id}/test endpoint)
# ─────────────────────────────────────────────────────────────────────────────


def probe_llm_connection(
    profile: "LLMProfileDocument | LLMProfileInternal",
    prompt: str = "Reply with the single word: OK",
    timeout_seconds: int = 15,
) -> dict:
    """
    Send a minimal test prompt to the LLM and return a result dict.

    Returns:
        {
            "success": bool,
            "message": str,
            "response_preview": str | None,
            "latency_ms": int | None,
        }
    """
    if litellm is None:
        return {
            "success": False,
            "message": "litellm is not installed. Run: uv add litellm",
            "response_preview": None,
            "latency_ms": None,
        }

    start = time.monotonic()
    try:
        llm = build_llm(profile)  # noqa: F841 – ensures crewai is available too

        provider = str(profile.provider)
        model_string = get_model_string(provider, str(profile.model))

        call_kwargs: dict = {
            "model": model_string,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 20,
            "temperature": 0.0,
            "timeout": timeout_seconds,
        }

        api_key = getattr(profile, "api_key", None)
        if api_key and provider not in _NO_KEY_PROVIDERS:
            call_kwargs["api_key"] = api_key

        base_url = getattr(profile, "base_url", None)
        if base_url:
            call_kwargs["api_base"] = base_url
        elif provider == "ollama":
            call_kwargs["api_base"] = settings.OLLAMA_BASE_URL

        response = litellm.completion(**call_kwargs)
        text = response.choices[0].message.content or ""
        latency_ms = int((time.monotonic() - start) * 1000)

        return {
            "success": True,
            "message": f"Connection successful ({latency_ms} ms)",
            "response_preview": text.strip()[:100],
            "latency_ms": latency_ms,
        }

    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        error_msg = str(exc)
        logger.warning(
            "LLM connection test failed for profile '%s': %s",
            getattr(profile, "name", "unknown"),
            error_msg,
        )
        return {
            "success": False,
            "message": f"Connection failed: {error_msg}",
            "response_preview": None,
            "latency_ms": latency_ms,
        }


# ─────────────────────────────────────────────────────────────────────────────
# LLMFactory class  (used by AgentFactory for session-scoped caching)
# ─────────────────────────────────────────────────────────────────────────────


class LLMFactory:
    """Async factory that builds and caches CrewAI LLM objects.

    Designed to be held as an attribute of :class:`~app.core.agent_factory.AgentFactory`
    so that the global default profile is queried from MongoDB at most once per
    pipeline run (lazy-loaded and cached on first use).

    No SQLAlchemy session is needed — all DB access goes through Beanie CRUD
    functions which use the global Motor client initialised at startup.

    Args:
        run_profile_id: Optional MongoDB ObjectId string of a run-level LLM
            profile override.  When provided, :meth:`build_default` returns an
            LLM built from this profile instead of the ``is_default=True`` one.
    """

    def __init__(self, run_profile_id: Optional[str] = None) -> None:
        self._run_profile_id = run_profile_id
        self._default_profile: Optional["LLMProfileDocument"] = None
        self._default_loaded: bool = False

    def build_from_profile(self, profile: "LLMProfileDocument | LLMProfileInternal"):
        """Build a CrewAI LLM from a concrete profile object.

        Args:
            profile: A :class:`~app.db.models.LLMProfileDocument` (Beanie) or
                a :class:`~app.schemas.llm_profile.LLMProfileInternal` (Pydantic).

        Returns:
            A ``crewai.LLM`` instance ready to be passed to a CrewAI Agent.
        """
        return build_llm(profile)

    async def build_default(self):
        """Build a LLM using the run-level or global default DB profile.

        Resolution order:

        1. Run-level profile (``run_profile_id`` supplied to the constructor).
        2. Global default profile (``is_default=True`` in MongoDB).
        3. Environment-variable fallback (``DEFAULT_LLM_*`` settings).

        Returns:
            A ``crewai.LLM`` instance.
        """
        profile = await self._load_default_profile()
        if profile is not None:
            return build_llm(profile)
        return build_fallback_llm()

    async def _load_default_profile(self) -> Optional["LLMProfileDocument"]:
        """Lazy-load the effective default LLM profile (cached per factory instance).

        When a ``run_profile_id`` was supplied to the constructor, that profile
        is fetched and cached.  Otherwise the collection-level
        ``is_default=True`` profile is used.

        Returns:
            The resolved :class:`~app.db.models.LLMProfileDocument`, or ``None``
            if neither a run-level profile nor a global default could be found.
        """
        if not self._default_loaded:
            self._default_loaded = True
            from app.db import crud

            if self._run_profile_id is not None:
                profile = await crud.get_llm_profile(self._run_profile_id)
                if profile is None:
                    logger.warning(
                        "[LLMFactory] Run-level profile id=%r not found; "
                        "falling back to global default.",
                        self._run_profile_id,
                    )
                    profile = await crud.get_default_llm_profile()
            else:
                profile = await crud.get_default_llm_profile()

            self._default_profile = profile

        return self._default_profile


# ─────────────────────────────────────────────────────────────────────────────
# Supported providers / models catalogue (used by the frontend dropdowns)
# ─────────────────────────────────────────────────────────────────────────────


PROVIDER_CATALOGUE: dict[str, dict] = {
    "openai": {
        "label": "OpenAI",
        "requires_api_key": True,
        "requires_base_url": False,
        "models": [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-3.5-turbo",
        ],
        "default_model": "gpt-4o",
    },
    "anthropic": {
        "label": "Anthropic",
        "requires_api_key": True,
        "requires_base_url": False,
        "models": [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
        ],
        "default_model": "claude-3-5-sonnet-20241022",
    },
    "ollama": {
        "label": "Ollama (Local)",
        "requires_api_key": False,
        "requires_base_url": True,
        "models": [
            "llama3",
            "llama3.1",
            "llama3.2",
            "mistral",
            "gemma2",
            "ibm-granite/granite-3.0-2b-instruct",
            "phi3",
            "qwen2.5",
        ],
        "default_model": "llama3",
        "default_base_url": "http://localhost:11434",
    },
    "groq": {
        "label": "Groq",
        "requires_api_key": True,
        "requires_base_url": False,
        "models": [
            "llama-3.1-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
            "gemma2-9b-it",
        ],
        "default_model": "llama-3.1-70b-versatile",
    },
    "azure_openai": {
        "label": "Azure OpenAI",
        "requires_api_key": True,
        "requires_base_url": True,
        "models": [
            "gpt-4o",
            "gpt-4-turbo",
            "gpt-35-turbo",
        ],
        "default_model": "gpt-4o",
    },
    "huggingface": {
        "label": "HuggingFace",
        "requires_api_key": True,
        "requires_base_url": False,
        "models": [
            "ibm-granite/granite-3.0-2b-instruct",
            "meta-llama/Meta-Llama-3-8B-Instruct",
            "mistralai/Mistral-7B-Instruct-v0.3",
        ],
        "default_model": "ibm-granite/granite-3.0-2b-instruct",
    },
    "lm_studio": {
        "label": "LM Studio (Local)",
        "requires_api_key": False,
        "requires_base_url": True,
        # Model name must match exactly what LM Studio shows in its UI.
        # These are common examples — the actual list depends on what
        # the user has downloaded in LM Studio.
        "models": [
            "granite-3.1-2b-instruct",
            "granite-3.1-8b-instruct",
            "llama-3.2-3b-instruct",
            "llama-3.1-8b-instruct",
            "mistral-7b-instruct-v0.3",
            "qwen2.5-7b-instruct",
            "phi-3.5-mini-instruct",
            "gemma-2-2b-instruct",
        ],
        "default_model": "granite-3.1-2b-instruct",
        "default_base_url": "http://localhost:1234/v1",
        "note": (
            "LM Studio exposes an OpenAI-compatible API. "
            "Start the Local Server in LM Studio before running the pipeline. "
            "The model name must exactly match the identifier shown in LM Studio."
        ),
    },
}
