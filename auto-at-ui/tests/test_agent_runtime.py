import pytest
from agents.shared.openrouter import OpenAICompatibleLanguageModel, create_language_model
from agents.shared.runtime import (
    AGENT_RUNTIME_CONFIG_KEY,
    AgentRuntimeConfig,
    AgentStepGuard,
    StepGuardPolicy,
    resolve_agent_runtime,
)
from config import Settings


def test_agent_runtime_uses_huggingface_environment_defaults() -> None:
    runtime = AgentRuntimeConfig.from_settings(Settings())

    assert runtime.provider == "huggingface"
    assert runtime.model == "Qwen/Qwen2.5-Coder-32B-Instruct"
    assert runtime.evidence.include_metadata
    assert runtime.evidence.include_redacted_text
    assert not runtime.evidence.include_screenshots
    assert runtime.guard.max_concurrency == 1


def test_tenant_override_can_switch_model_evidence_and_fallback() -> None:
    runtime = resolve_agent_runtime(
        Settings(),
        {
            "model": "anthropic/claude-sonnet",
            "evidence": {"include_redacted_text": False, "include_screenshots": True},
            "fallback": {"provider": "openrouter", "model": "google/gemini-flash"},
        },
    )

    assert runtime.model == "anthropic/claude-sonnet"
    assert runtime.evidence.include_metadata
    assert runtime.evidence.include_screenshots
    assert runtime.fallback is not None
    assert runtime.fallback.model == "google/gemini-flash"
    assert AGENT_RUNTIME_CONFIG_KEY == "agent.runtime.v1"


def test_step_guard_rejects_budget_and_evidence_limit_before_calling_a_model() -> None:
    guard = AgentStepGuard(
        StepGuardPolicy(
            max_tokens=100,
            max_steps_per_run=1,
            max_evidence_bytes_per_step=1024,
            max_concurrency=1,
        )
    )

    assert not guard.allow_next_step(requested_tokens=101, evidence_bytes=1)
    assert not guard.allow_next_step(requested_tokens=100, evidence_bytes=1025)
    assert guard.allow_next_step(requested_tokens=100, evidence_bytes=1024)
    assert not guard.allow_next_step(requested_tokens=1, evidence_bytes=1)


def test_runtime_rejects_an_adapter_that_has_not_been_installed() -> None:
    with pytest.raises(ValueError, match="adapter"):
        AgentRuntimeConfig.model_validate(
            {
                "provider": "direct-provider",
                "model": "example/model",
                "guard": {
                    "max_tokens": 100,
                    "max_steps_per_run": 1,
                    "max_evidence_bytes_per_step": 1024,
                },
            }
        )


def test_huggingface_runtime_uses_its_environment_gateway() -> None:
    runtime = AgentRuntimeConfig.model_validate(
        {
            "provider": "huggingface",
            "model": "Qwen/Qwen2.5-Coder-32B-Instruct",
            "guard": {
                "max_tokens": 100,
                "max_steps_per_run": 1,
                "max_evidence_bytes_per_step": 1024,
            },
        }
    )

    model = create_language_model(
        Settings(huggingface_api_key="hf_test", huggingface_base_url="https://hf.example/v1"),
        runtime,
    )

    assert isinstance(model, OpenAICompatibleLanguageModel)
