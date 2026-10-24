"""Pure Vision provider capabilities; no credentials, environment or network access."""

from dataclasses import dataclass
from typing import Literal

VisionProviderId = Literal["huggingface", "gemini", "codex_cli"]
CODEX_VISION_MODEL = "gpt-6-luna"
GEMINI_VISION_MODEL = "gemini-3.8-flash"
HUGGINGFACE_VISION_MODEL = "Qwen/Qwen3.8-27B:deepinfra"
VISION_MODEL_TIMEOUT_SECONDS = 120.0


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
)


def validate_vision_model(provider: VisionProviderId, model: str) -> None:
    if not model.strip():
        raise ValueError("vision requires a configured model")
    if provider == "gemini" and model != GEMINI_VISION_MODEL:
        raise ValueError("unsupported Gemini vision model")
    if provider == "codex_cli" and model != CODEX_VISION_MODEL:
        raise ValueError("unsupported Codex vision model")
