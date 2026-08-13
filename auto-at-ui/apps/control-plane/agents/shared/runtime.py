"""Validated, provider-neutral configuration and guards for agent execution."""

from collections.abc import Mapping

from config import Settings
from pydantic import BaseModel, Field, model_validator

AGENT_RUNTIME_CONFIG_KEY = "agent.runtime.v1"


class EvidencePolicy(BaseModel):
    include_metadata: bool = True
    include_redacted_text: bool = True
    include_screenshots: bool = False


class StepGuardPolicy(BaseModel):
    max_tokens: int = Field(ge=1, le=100_000)
    max_steps_per_run: int = Field(ge=1, le=10)
    max_evidence_bytes_per_step: int = Field(ge=1_024, le=5_000_000)
    max_concurrency: int = Field(default=1, ge=1, le=100)


class FallbackModel(BaseModel):
    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=200)


class AgentRuntimeConfig(BaseModel):
    """Non-secret values that may later be changed by the admin interface."""

    provider: str = Field(default="huggingface", min_length=1, max_length=100)
    model: str = Field(default="Qwen/Qwen2.5-Coder-32B-Instruct", min_length=1, max_length=200)
    evidence: EvidencePolicy = Field(default_factory=EvidencePolicy)
    guard: StepGuardPolicy
    fallback: FallbackModel | None = None

    @model_validator(mode="after")
    def requires_an_installed_provider_adapter(self) -> "AgentRuntimeConfig":
        if self.provider not in {"huggingface", "openrouter"}:
            raise ValueError("the configured provider adapter is not installed")
        return self

    @classmethod
    def from_settings(cls, settings: Settings) -> "AgentRuntimeConfig":
        fallback = None
        if settings.agent_fallback_enabled:
            if not settings.agent_fallback_provider or not settings.agent_fallback_model:
                raise ValueError(
                    "fallback provider and model are required when fallback is enabled"
                )
            fallback = FallbackModel(
                provider=settings.agent_fallback_provider,
                model=settings.agent_fallback_model,
            )
        return cls(
            provider=settings.agent_provider,
            model=settings.agent_model,
            evidence=EvidencePolicy(
                include_metadata=settings.agent_evidence_metadata_enabled,
                include_redacted_text=settings.agent_evidence_redacted_text_enabled,
                include_screenshots=settings.agent_evidence_screenshots_enabled,
            ),
            guard=StepGuardPolicy(
                max_tokens=settings.agent_step_max_tokens,
                max_steps_per_run=settings.agent_max_steps_per_run,
                max_evidence_bytes_per_step=settings.agent_max_evidence_bytes_per_step,
                max_concurrency=settings.agent_max_concurrency,
            ),
            fallback=fallback,
        )

    def with_override(self, override: Mapping[str, object] | None) -> "AgentRuntimeConfig":
        """Validate one tenant's non-secret database override over environment defaults."""
        if override is None:
            return self
        return type(self).model_validate(_merge(self.model_dump(), override))


class AgentStepGuard:
    """In-memory guard for one triage run; a workflow owns its lifecycle."""

    def __init__(self, policy: StepGuardPolicy) -> None:
        self._policy = policy
        self._used_steps = 0

    def allow_next_step(self, *, requested_tokens: int, evidence_bytes: int) -> bool:
        if requested_tokens > self._policy.max_tokens:
            return False
        if evidence_bytes > self._policy.max_evidence_bytes_per_step:
            return False
        if self._used_steps >= self._policy.max_steps_per_run:
            return False
        self._used_steps += 1
        return True


def resolve_agent_runtime(
    settings: Settings, stored_override: Mapping[str, object] | None
) -> AgentRuntimeConfig:
    """Resolve environment bootstrap defaults with one tenant's DB-managed policy."""
    return AgentRuntimeConfig.from_settings(settings).with_override(stored_override)


def _merge(defaults: dict[str, object], override: Mapping[str, object]) -> dict[str, object]:
    """Merge nested JSON configuration without forcing an admin to resubmit defaults."""
    merged = defaults.copy()
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, Mapping):
            merged[key] = _merge(current, value)
        else:
            merged[key] = value
    return merged
