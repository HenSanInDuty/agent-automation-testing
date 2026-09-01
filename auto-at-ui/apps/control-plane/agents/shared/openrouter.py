"""OpenAI-compatible gateway adapters for approved language-model providers."""

from typing import Any

import httpx
from config import Settings
from huggingface_hub import AsyncInferenceClient

from agents.shared.models import LanguageModel
from agents.shared.runtime import AgentRuntimeConfig, VisionPolicy


class OpenAICompatibleLanguageModel:
    """Minimal OpenAI-compatible adapter; model selection stays in runtime config."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._transport = transport

    async def ainvoke(self, payload: Any, **kwargs: Any) -> Any:
        request = {"model": self._model, **payload}
        request.update(kwargs)
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=30.0, transport=self._transport
        ) as client:
            response = await client.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=request,
            )
        response.raise_for_status()
        return response.json()


class HuggingFaceVisionLanguageModel:
    """Provider-aware multimodal transport that keeps raw bytes in memory."""

    def __init__(self, *, api_key: str, model: str, timeout_seconds: float = 30) -> None:
        base_model, separator, provider = model.partition(":")
        self._client = AsyncInferenceClient(
            model=base_model,
            provider=provider if separator else "auto",
            api_key=api_key,
            timeout=timeout_seconds,
        )

    async def ainvoke(self, payload: Any, **kwargs: Any) -> Any:
        response = await self._client.chat_completion(
            messages=payload["messages"],
            max_tokens=payload.get("max_tokens"),
            temperature=payload.get("temperature"),
            **kwargs,
        )
        return {"choices": [{"message": {"content": response.choices[0].message.content}}]}


def create_language_model(settings: Settings, runtime: AgentRuntimeConfig) -> LanguageModel:
    """Construct an approved gateway adapter; no model call occurs here."""
    if runtime.provider == "huggingface":
        if not settings.huggingface_api_key:
            raise ValueError("HUGGINGFACE_API_KEY must be set before invoking an agent")
        return OpenAICompatibleLanguageModel(
            api_key=settings.huggingface_api_key,
            base_url=settings.huggingface_base_url,
            model=runtime.model,
        )
    if runtime.provider == "openrouter":
        if not settings.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY must be set before invoking an agent")
        return OpenAICompatibleLanguageModel(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            model=runtime.model,
        )
    raise ValueError(f"unsupported language-model provider: {runtime.provider}")


def create_vision_language_model(settings: Settings, policy: VisionPolicy) -> LanguageModel:
    """Construct the vision-only Hugging Face gateway from its own policy."""
    if policy.provider != "huggingface":
        raise ValueError(f"unsupported vision provider: {policy.provider}")
    if not settings.huggingface_api_key:
        raise ValueError("HUGGINGFACE_API_KEY must be set before invoking vision")
    if policy.model.endswith((":cohere", ":baseten", ":deepinfra")):
        # These Hugging Face VLM routes document the OpenAI-compatible
        # image_url chat-completion format. Keep the provider-aware client for
        # routes that require its custom transport.
        return OpenAICompatibleLanguageModel(
            api_key=settings.huggingface_api_key,
            base_url=settings.huggingface_base_url,
            model=policy.model,
        )
    return HuggingFaceVisionLanguageModel(
        api_key=settings.huggingface_api_key,
        model=policy.model,
        timeout_seconds=policy.max_session_seconds,
    )
