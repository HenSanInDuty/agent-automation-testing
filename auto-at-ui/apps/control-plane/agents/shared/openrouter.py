"""OpenAI-compatible gateway adapters for approved language-model providers."""

from typing import Any

import httpx
from config import Settings

from agents.shared.models import LanguageModel
from agents.shared.runtime import AgentRuntimeConfig


class OpenAICompatibleLanguageModel:
    """Minimal OpenAI-compatible adapter; model selection stays in runtime config."""

    def __init__(self, *, api_key: str, base_url: str, model: str) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def ainvoke(self, payload: Any, **kwargs: Any) -> Any:
        request = {"model": self._model, **payload}
        request.update(kwargs)
        async with httpx.AsyncClient(base_url=self._base_url, timeout=30.0) as client:
            response = await client.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=request,
            )
        response.raise_for_status()
        return response.json()


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
