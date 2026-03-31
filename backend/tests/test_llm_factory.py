"""
tests/test_llm_factory.py
─────────────────────────
Unit tests for app/core/llm_factory.py

Run with:
    cd backend
    uv run pytest tests/test_llm_factory.py -v
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.llm_factory import (
    PROVIDER_CATALOGUE,
    LLMFactory,
    build_fallback_llm,
    build_llm,
    get_model_string,
    probe_llm_connection,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_profile(**kwargs) -> SimpleNamespace:
    """
    Create a lightweight fake LLMProfile object (no DB required).
    Defaults to a sensible OpenAI profile so tests only override what they need.
    """
    defaults = dict(
        id=1,
        name="Test Profile",
        provider="openai",
        model="gpt-4o",
        api_key="sk-test-key-1234",
        base_url=None,
        temperature=0.1,
        max_tokens=2048,
        is_default=False,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ─────────────────────────────────────────────────────────────────────────────
# get_model_string
# ─────────────────────────────────────────────────────────────────────────────


class TestGetModelString:
    def test_openai(self):
        assert get_model_string("openai", "gpt-4o") == "openai/gpt-4o"

    def test_anthropic(self):
        assert (
            get_model_string("anthropic", "claude-3-5-sonnet-20241022")
            == "anthropic/claude-3-5-sonnet-20241022"
        )

    def test_ollama(self):
        assert get_model_string("ollama", "llama3") == "ollama/llama3"

    def test_groq(self):
        assert (
            get_model_string("groq", "llama-3.1-70b-versatile")
            == "groq/llama-3.1-70b-versatile"
        )

    def test_azure_openai(self):
        assert get_model_string("azure_openai", "gpt-4o") == "azure/gpt-4o"

    def test_huggingface(self):
        assert (
            get_model_string("huggingface", "ibm-granite/granite-3.0-2b-instruct")
            == "huggingface/ibm-granite/granite-3.0-2b-instruct"
        )

    def test_unsupported_provider_raises(self):
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            get_model_string("unknown_provider", "some-model")

    def test_unsupported_provider_lists_supported(self):
        """Error message should include the list of valid providers."""
        with pytest.raises(ValueError) as exc_info:
            get_model_string("bedrock", "titan")
        msg = str(exc_info.value)
        assert "openai" in msg
        assert "anthropic" in msg
        assert "ollama" in msg

    def test_model_with_slash(self):
        """HuggingFace models contain slashes — they must be preserved."""
        result = get_model_string("huggingface", "meta-llama/Meta-Llama-3-8B-Instruct")
        assert result == "huggingface/meta-llama/Meta-Llama-3-8B-Instruct"

    @pytest.mark.parametrize(
        "provider,model,expected",
        [
            ("openai", "gpt-3.5-turbo", "openai/gpt-3.5-turbo"),
            ("anthropic", "claude-3-opus-20240229", "anthropic/claude-3-opus-20240229"),
            ("ollama", "mistral", "ollama/mistral"),
            ("groq", "gemma2-9b-it", "groq/gemma2-9b-it"),
        ],
    )
    def test_parametrized_providers(self, provider, model, expected):
        assert get_model_string(provider, model) == expected


# ─────────────────────────────────────────────────────────────────────────────
# build_llm
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildLlm:
    @patch("app.core.llm_factory.LLM")
    def test_openai_basic(self, MockLLM):
        profile = _make_profile(provider="openai", model="gpt-4o", api_key="sk-abc")
        build_llm(profile)

        MockLLM.assert_called_once()
        call_kwargs = MockLLM.call_args.kwargs
        assert call_kwargs["model"] == "openai/gpt-4o"
        assert call_kwargs["api_key"] == "sk-abc"
        assert call_kwargs["temperature"] == 0.1
        assert call_kwargs["max_tokens"] == 2048

    @patch("app.core.llm_factory.LLM")
    def test_anthropic_basic(self, MockLLM):
        profile = _make_profile(
            provider="anthropic",
            model="claude-3-5-sonnet-20241022",
            api_key="sk-ant-test",
            temperature=0.0,
            max_tokens=4096,
        )
        build_llm(profile)

        call_kwargs = MockLLM.call_args.kwargs
        assert call_kwargs["model"] == "anthropic/claude-3-5-sonnet-20241022"
        assert call_kwargs["api_key"] == "sk-ant-test"
        assert call_kwargs["temperature"] == 0.0
        assert call_kwargs["max_tokens"] == 4096

    @patch("app.core.llm_factory.LLM")
    def test_ollama_no_api_key(self, MockLLM):
        """Ollama is a local provider — api_key must NOT be passed."""
        profile = _make_profile(
            provider="ollama",
            model="llama3",
            api_key=None,
            base_url="http://localhost:11434",
        )
        build_llm(profile)

        call_kwargs = MockLLM.call_args.kwargs
        assert call_kwargs["model"] == "ollama/llama3"
        assert "api_key" not in call_kwargs or call_kwargs.get("api_key") is None
        assert call_kwargs["base_url"] == "http://localhost:11434"

    @patch("app.core.llm_factory.LLM")
    def test_ollama_default_base_url(self, MockLLM):
        """When base_url is None for Ollama, the factory injects the default."""
        profile = _make_profile(
            provider="ollama",
            model="llama3",
            api_key=None,
            base_url=None,
        )
        build_llm(profile)

        call_kwargs = MockLLM.call_args.kwargs
        assert call_kwargs["base_url"] == "http://localhost:11434"

    @patch("app.core.llm_factory.LLM")
    def test_custom_base_url_is_passed_through(self, MockLLM):
        """A non-Ollama profile with a custom base_url should forward it."""
        profile = _make_profile(
            provider="openai",
            model="gpt-4o",
            api_key="sk-test",
            base_url="http://custom-proxy.internal/v1",
        )
        build_llm(profile)

        call_kwargs = MockLLM.call_args.kwargs
        assert call_kwargs["base_url"] == "http://custom-proxy.internal/v1"

    @patch("app.core.llm_factory.LLM")
    def test_no_base_url_not_in_kwargs(self, MockLLM):
        """When base_url is None for a non-Ollama provider, key must be absent."""
        profile = _make_profile(
            provider="openai",
            model="gpt-4o",
            api_key="sk-test",
            base_url=None,
        )
        build_llm(profile)

        call_kwargs = MockLLM.call_args.kwargs
        assert "base_url" not in call_kwargs

    @patch("app.core.llm_factory.LLM")
    def test_temperature_and_max_tokens_float_int(self, MockLLM):
        """temperature should be float, max_tokens should be int."""
        profile = _make_profile(
            provider="openai",
            model="gpt-4o",
            temperature=0.7,
            max_tokens=1024,
        )
        build_llm(profile)

        call_kwargs = MockLLM.call_args.kwargs
        assert isinstance(call_kwargs["temperature"], float)
        assert isinstance(call_kwargs["max_tokens"], int)

    @patch("app.core.llm_factory.LLM")
    def test_returns_llm_instance(self, MockLLM):
        """build_llm should return the value that LLM() constructor produces."""
        expected = object()
        MockLLM.return_value = expected

        profile = _make_profile()
        result = build_llm(profile)

        assert result is expected

    def test_missing_crewai_raises_import_error(self):
        """If LLM is None (crewai not installed), build_llm must raise ImportError."""
        import app.core.llm_factory as mod

        original_llm = mod.LLM
        mod.LLM = None
        try:
            with pytest.raises(ImportError, match="crewai"):
                build_llm(_make_profile())
        finally:
            mod.LLM = original_llm

    @patch("app.core.llm_factory.LLM")
    def test_groq_profile(self, MockLLM):
        profile = _make_profile(
            provider="groq",
            model="llama-3.1-70b-versatile",
            api_key="gsk-test",
        )
        build_llm(profile)

        call_kwargs = MockLLM.call_args.kwargs
        assert call_kwargs["model"] == "groq/llama-3.1-70b-versatile"
        assert call_kwargs["api_key"] == "gsk-test"

    @patch("app.core.llm_factory.LLM")
    def test_huggingface_profile(self, MockLLM):
        profile = _make_profile(
            provider="huggingface",
            model="ibm-granite/granite-3.0-2b-instruct",
            api_key="hf_test_token",
        )
        build_llm(profile)

        call_kwargs = MockLLM.call_args.kwargs
        assert call_kwargs["model"] == "huggingface/ibm-granite/granite-3.0-2b-instruct"

    @patch("app.core.llm_factory.LLM")
    def test_no_api_key_warning_logged(self, MockLLM, caplog):
        """When a key-required provider has no api_key, a warning should be logged."""
        import logging

        profile = _make_profile(provider="openai", model="gpt-4o", api_key=None)
        with caplog.at_level(logging.WARNING, logger="app.core.llm_factory"):
            build_llm(profile)

        assert any("no api_key" in record.message for record in caplog.records)


# ─────────────────────────────────────────────────────────────────────────────
# build_fallback_llm
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildFallbackLlm:
    @patch("app.core.llm_factory.LLM")
    @patch("app.core.llm_factory.settings")
    def test_uses_env_settings(self, mock_settings, MockLLM):
        mock_settings.DEFAULT_LLM_PROVIDER = "openai"
        mock_settings.DEFAULT_LLM_MODEL = "gpt-4o-mini"
        mock_settings.DEFAULT_LLM_API_KEY = "sk-env-key"
        mock_settings.DEFAULT_LLM_BASE_URL = None
        mock_settings.DEFAULT_LLM_TEMPERATURE = 0.2
        mock_settings.DEFAULT_LLM_MAX_TOKENS = 512

        build_fallback_llm()

        call_kwargs = MockLLM.call_args.kwargs
        assert call_kwargs["model"] == "openai/gpt-4o-mini"
        assert call_kwargs["api_key"] == "sk-env-key"
        assert call_kwargs["temperature"] == 0.2
        assert call_kwargs["max_tokens"] == 512

    @patch("app.core.llm_factory.LLM")
    @patch("app.core.llm_factory.settings")
    def test_no_api_key_key_not_in_kwargs(self, mock_settings, MockLLM):
        mock_settings.DEFAULT_LLM_PROVIDER = "openai"
        mock_settings.DEFAULT_LLM_MODEL = "gpt-4o"
        mock_settings.DEFAULT_LLM_API_KEY = None
        mock_settings.DEFAULT_LLM_BASE_URL = None
        mock_settings.DEFAULT_LLM_TEMPERATURE = 0.1
        mock_settings.DEFAULT_LLM_MAX_TOKENS = 2048

        build_fallback_llm()

        call_kwargs = MockLLM.call_args.kwargs
        assert "api_key" not in call_kwargs

    @patch("app.core.llm_factory.LLM")
    @patch("app.core.llm_factory.settings")
    def test_ollama_fallback_gets_default_base_url(self, mock_settings, MockLLM):
        mock_settings.DEFAULT_LLM_PROVIDER = "ollama"
        mock_settings.DEFAULT_LLM_MODEL = "llama3"
        mock_settings.DEFAULT_LLM_API_KEY = None
        mock_settings.DEFAULT_LLM_BASE_URL = None
        mock_settings.DEFAULT_LLM_TEMPERATURE = 0.1
        mock_settings.DEFAULT_LLM_MAX_TOKENS = 2048

        build_fallback_llm()

        call_kwargs = MockLLM.call_args.kwargs
        assert call_kwargs["base_url"] == "http://localhost:11434"

    @patch("app.core.llm_factory.LLM")
    @patch("app.core.llm_factory.settings")
    def test_custom_base_url_from_env(self, mock_settings, MockLLM):
        mock_settings.DEFAULT_LLM_PROVIDER = "openai"
        mock_settings.DEFAULT_LLM_MODEL = "gpt-4o"
        mock_settings.DEFAULT_LLM_API_KEY = "sk-test"
        mock_settings.DEFAULT_LLM_BASE_URL = "http://my-proxy.internal/v1"
        mock_settings.DEFAULT_LLM_TEMPERATURE = 0.1
        mock_settings.DEFAULT_LLM_MAX_TOKENS = 2048

        build_fallback_llm()

        call_kwargs = MockLLM.call_args.kwargs
        assert call_kwargs["base_url"] == "http://my-proxy.internal/v1"


# ─────────────────────────────────────────────────────────────────────────────
# LLMFactory class
# ─────────────────────────────────────────────────────────────────────────────


class TestLLMFactory:
    def _make_factory(self, default_profile=None) -> LLMFactory:
        """Create an LLMFactory with a mocked DB session."""
        db = MagicMock()
        db.scalar.return_value = default_profile
        factory = LLMFactory(db)
        return factory

    @patch("app.core.llm_factory.build_llm")
    def test_build_from_profile_delegates_to_build_llm(self, mock_build_llm):
        factory = self._make_factory()
        profile = _make_profile()
        factory.build_from_profile(profile)
        mock_build_llm.assert_called_once_with(profile)

    @patch("app.core.llm_factory.build_llm")
    def test_build_default_uses_db_profile_when_available(self, mock_build_llm):
        db_profile = _make_profile(name="DB Default", is_default=True)
        factory = self._make_factory(default_profile=db_profile)

        factory.build_default()

        mock_build_llm.assert_called_once_with(db_profile)

    @patch("app.core.llm_factory.build_fallback_llm")
    def test_build_default_falls_back_to_env_when_no_db_profile(self, mock_fallback):
        factory = self._make_factory(default_profile=None)
        factory.build_default()
        mock_fallback.assert_called_once()

    @patch("app.core.llm_factory.build_llm")
    def test_default_profile_is_cached(self, mock_build_llm):
        """DB must be queried only once even when build_default is called twice."""
        db_profile = _make_profile(name="DB Default", is_default=True)
        factory = self._make_factory(default_profile=db_profile)

        factory.build_default()
        factory.build_default()

        # DB.scalar should have been called exactly once (cache hit on 2nd call)
        assert factory._db.scalar.call_count == 1

    @patch("app.core.llm_factory.build_llm")
    def test_build_from_profile_returns_llm_result(self, mock_build_llm):
        expected = object()
        mock_build_llm.return_value = expected

        factory = self._make_factory()
        result = factory.build_from_profile(_make_profile())

        assert result is expected


# ─────────────────────────────────────────────────────────────────────────────
# test_llm_connection
# ─────────────────────────────────────────────────────────────────────────────


class TestLlmConnection:
    @patch("app.core.llm_factory.build_llm")  # prevent real LLM construction
    @patch("app.core.llm_factory.litellm")
    def test_success_returns_expected_shape(self, mock_litellm, mock_build_llm):
        # Fake litellm response
        fake_choice = SimpleNamespace(message=SimpleNamespace(content="OK"))
        mock_litellm.completion.return_value = SimpleNamespace(choices=[fake_choice])

        profile = _make_profile()
        result = probe_llm_connection(profile)

        assert result["success"] is True
        assert "latency_ms" in result
        assert isinstance(result["latency_ms"], int)
        assert result["response_preview"] == "OK"

    @patch("app.core.llm_factory.build_llm")
    @patch("app.core.llm_factory.litellm")
    def test_failure_returns_success_false(self, mock_litellm, mock_build_llm):
        mock_litellm.completion.side_effect = RuntimeError("Connection refused")

        profile = _make_profile()
        result = probe_llm_connection(profile)

        assert result["success"] is False
        assert "Connection refused" in result["message"]
        assert result["response_preview"] is None

    @patch("app.core.llm_factory.build_llm")
    @patch("app.core.llm_factory.litellm")
    def test_response_preview_is_truncated(self, mock_litellm, mock_build_llm):
        long_response = "x" * 500
        fake_choice = SimpleNamespace(message=SimpleNamespace(content=long_response))
        mock_litellm.completion.return_value = SimpleNamespace(choices=[fake_choice])

        profile = _make_profile()
        result = probe_llm_connection(profile)

        assert len(result["response_preview"]) <= 100

    @patch("app.core.llm_factory.build_llm")
    @patch("app.core.llm_factory.litellm")
    def test_ollama_uses_correct_api_base(self, mock_litellm, mock_build_llm):
        fake_choice = SimpleNamespace(message=SimpleNamespace(content="OK"))
        mock_litellm.completion.return_value = SimpleNamespace(choices=[fake_choice])

        profile = _make_profile(
            provider="ollama",
            model="llama3",
            api_key=None,
            base_url="http://localhost:11434",
        )
        probe_llm_connection(profile)

        call_kwargs = mock_litellm.completion.call_args.kwargs
        assert call_kwargs.get("api_base") == "http://localhost:11434"

    @patch("app.core.llm_factory.build_llm")
    @patch("app.core.llm_factory.litellm")
    def test_openai_api_key_forwarded(self, mock_litellm, mock_build_llm):
        fake_choice = SimpleNamespace(message=SimpleNamespace(content="OK"))
        mock_litellm.completion.return_value = SimpleNamespace(choices=[fake_choice])

        profile = _make_profile(
            provider="openai",
            model="gpt-4o",
            api_key="sk-real-key",
        )
        probe_llm_connection(profile)

        call_kwargs = mock_litellm.completion.call_args.kwargs
        assert call_kwargs.get("api_key") == "sk-real-key"


# ─────────────────────────────────────────────────────────────────────────────
# PROVIDER_CATALOGUE
# ─────────────────────────────────────────────────────────────────────────────


class TestProviderCatalogue:
    def test_all_providers_present(self):
        expected = {
            "openai",
            "anthropic",
            "ollama",
            "groq",
            "azure_openai",
            "huggingface",
            "lm_studio",
        }
        assert set(PROVIDER_CATALOGUE.keys()) == expected

    def test_each_entry_has_required_keys(self):
        required_keys = {
            "label",
            "requires_api_key",
            "requires_base_url",
            "models",
            "default_model",
        }
        for provider, info in PROVIDER_CATALOGUE.items():
            missing = required_keys - info.keys()
            assert not missing, f"Provider {provider!r} missing keys: {missing}"

    def test_models_are_non_empty_lists(self):
        for provider, info in PROVIDER_CATALOGUE.items():
            assert isinstance(info["models"], list), (
                f"{provider}: 'models' must be a list"
            )
            assert len(info["models"]) > 0, f"{provider}: 'models' must not be empty"

    def test_default_model_is_in_models_list(self):
        for provider, info in PROVIDER_CATALOGUE.items():
            assert info["default_model"] in info["models"], (
                f"{provider}: default_model={info['default_model']!r} "
                f"not in models list {info['models']}"
            )

    def test_ollama_requires_base_url(self):
        assert PROVIDER_CATALOGUE["ollama"]["requires_base_url"] is True

    def test_ollama_does_not_require_api_key(self):
        assert PROVIDER_CATALOGUE["ollama"]["requires_api_key"] is False

    def test_openai_requires_api_key(self):
        assert PROVIDER_CATALOGUE["openai"]["requires_api_key"] is True

    def test_granite_in_ollama_models(self):
        """ibm-granite must be available as an Ollama model option."""
        assert (
            "ibm-granite/granite-3.0-2b-instruct"
            in PROVIDER_CATALOGUE["ollama"]["models"]
        )
