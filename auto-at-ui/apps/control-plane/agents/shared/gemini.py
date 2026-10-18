"""Vision-only Gemini HTTP transport; a single bounded request with no fallback."""

import asyncio
import math
from time import monotonic
from typing import Any

import httpx
from auto_at.contracts.vision import VisualAction
from pydantic import TypeAdapter

from agents.shared.vision_providers import validate_vision_model
from agents.vision.diagnostics import (
    VisionProviderFailure,
    VisualDiagnosticCode,
    VisualDiagnosticFailure,
)

GEMINI_CHAT_COMPLETIONS_URL = (
    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
)


def _candidate_response_format(max_candidates: int) -> dict[str, Any]:
    """Derive provider constraints from the same contract used to validate replies."""
    if type(max_candidates) is not int or not 1 <= max_candidates <= 20:
        raise ValueError("candidate batch cap is invalid")
    schema = TypeAdapter(VisualAction).json_schema()
    definitions = schema.get("$defs", {})

    def inline(value):
        if isinstance(value, list):
            return [inline(item) for item in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            return inline(definitions[value["$ref"].rsplit("/", 1)[-1]])
        result = {
            ("anyOf" if key == "oneOf" else key): inline(item)
            for key, item in value.items()
            if key not in {"$defs", "discriminator", "title", "default", "const"}
        }
        if "const" in value:
            result["enum"] = [value["const"]]
        if "kind" in result.get("properties", {}):
            result["required"] = list(dict.fromkeys([*result.get("required", []), "kind"]))
        return result

    return {
        "type": "json_schema",
        "json_schema": {
            "name": "visual_candidates",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["candidates"],
                "properties": {
                    "candidates": {
                        "type": "array", "minItems": 1, "maxItems": max_candidates,
                        "items": inline(schema),
                    },
                },
            },
        },
    }


class GeminiVisionLanguageModel:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        timeout_seconds: float = 30,
        transport: httpx.AsyncBaseTransport | None = None,
        max_candidates: int | None = None,
    ) -> None:
        validate_vision_model("gemini", model)
        if not math.isfinite(timeout_seconds):
            raise ValueError("vision deadline must be finite")
        self._api_key = api_key
        self._model = model
        self._deadline = monotonic() + timeout_seconds
        self._transport = transport
        self._response_format = (
            _candidate_response_format(max_candidates)
            if max_candidates is not None else {"type": "json_object"}
        )

    async def ainvoke(self, payload: Any, **kwargs: Any) -> Any:
        if not self._api_key:
            raise VisionProviderFailure("provider_not_configured")
        remaining = min(30.0, self._deadline - monotonic())
        if remaining <= 0:
            raise VisionProviderFailure("provider_timeout", provider_category="timeout")
        # Explicit serialization prevents callers from overriding identity, endpoint,
        # authorization, reasoning, tools or streaming through arbitrary extra fields.
        tokens = payload.get("max_tokens")
        if type(tokens) is not int or not 1 <= tokens <= 100_000:
            raise ValueError("vision token cap is invalid")
        request = {
            "model": self._model,
            "messages": payload["messages"],
            "max_tokens": tokens,
            "temperature": payload.get("temperature", 0),
            "response_format": self._response_format,
            "reasoning_effort": "low",
        }
        try:
            async with asyncio.timeout(remaining), httpx.AsyncClient(
                timeout=remaining, transport=self._transport, follow_redirects=False,
            ) as client:
                response = await client.post(
                    GEMINI_CHAT_COMPLETIONS_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=request,
                )
        except (TimeoutError, httpx.TimeoutException):
            raise VisionProviderFailure(
                "provider_timeout", provider_category="timeout"
            ) from None
        except httpx.TransportError:
            raise VisionProviderFailure(
                "provider_unavailable", provider_category="transport"
            ) from None
        if not response.is_success:
            raise VisionProviderFailure.from_status(response.status_code)
        try:
            return response.json()
        except ValueError:
            raise VisualDiagnosticFailure(VisualDiagnosticCode.INVALID_JSON) from None
