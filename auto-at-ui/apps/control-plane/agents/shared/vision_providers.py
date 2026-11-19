"""Pure Vision provider capabilities; no credentials, environment or network access."""

from dataclasses import dataclass
from typing import Literal

from auto_at.contracts.codex_bridge import BRIDGE_PROVIDER_MODELS, BRIDGE_PROVIDERS

VisionProviderId = Literal["huggingface", "gemini", "codex_cli", "claude_cli"]
CODEX_VISION_MODEL = BRIDGE_PROVIDER_MODELS["codex_cli"]
CLAUDE_CLI_VISION_MODEL = BRIDGE_PROVIDER_MODELS["claude_cli"]
GEMINI_VISION_MODEL = "gemini-3.8-flash"
HUGGINGFACE_VISION_MODEL = "Qwen/Qwen3.8-27B:deepinfra"
VISION_MODEL_TIMEOUT_SECONDS = 120.0
# Providers served by the local DOM-first CLI bridge (codex exec / claude -p).
BRIDGE_VISION_PROVIDERS = BRIDGE_PROVIDERS


@dataclass(frozen=True)
class VisionProvider:
    id: VisionProviderId
    display_name: str
    models: tuple[str, ...]
    supports_inline_images: bool


VISION_PROVIDERS = (
    VisionProvider("huggingface", "Hugging Face", (HUGGINGFACE_VISION_MODEL,), False),
    VisionProvider("gemini", "Gehihi (Google Gemini)", (GEMINI_VISION_MODEL,), True),
    VisionProvider("codex_cli", "Codex (OpenAI, local bridge)", (CODEX_VISION_MODEL,), False),
    VisionProvider(
        "claude_cli", "Claude (claude -p, local bridge)", (CLAUDE_CLI_VISION_MODEL,), False,
    ),
)

INLINE_IMAGE_PROVIDERS = frozenset(p.id for p in VISION_PROVIDERS if p.supports_inline_images)


def is_bridge_provider(provider: str | None) -> bool:
    return provider in BRIDGE_VISION_PROVIDERS


def validate_vision_model(provider: VisionProviderId, model: str) -> None:
    if not model.strip():
        raise ValueError("vision requires a configured model")
    if provider == "gemini" and model != GEMINI_VISION_MODEL:
        raise ValueError("unsupported Gemini vision model")
    if is_bridge_provider(provider) and model != BRIDGE_PROVIDER_MODELS[provider]:
        raise ValueError("unsupported bridge vision model")
