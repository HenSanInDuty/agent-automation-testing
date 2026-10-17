"""Pure Vision provider capabilities; no credentials, environment or network access."""

from dataclasses import dataclass
from typing import Literal

VisionProviderId = Literal["huggingface", "gemini"]
GEMINI_VISION_MODEL = "gemini-3.8-flash"
HUGGINGFACE_VISION_MODEL = "Qwen/Qwen3.8-27B:deepinfra"


@dataclass(frozen=True)
class VisionProvider:
    id: VisionProviderId
    display_name: str
    models: tuple[str, ...]
    supports_inline_images: bool


VISION_PROVIDERS = (
    VisionProvider("huggingface", "Hugging Face", (HUGGINGFACE_VISION_MODEL,), False),
    VisionProvider("gemini", "Gehihi (Google Gemini)", (GEMINI_VISION_MODEL,), True),
)


def validate_vision_model(provider: VisionProviderId, model: str) -> None:
    if not model.strip():
        raise ValueError("vision requires a configured model")
    if provider == "gemini" and model != GEMINI_VISION_MODEL:
        raise ValueError("unsupported Gemini vision model")
