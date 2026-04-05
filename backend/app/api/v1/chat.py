from __future__ import annotations

import json
import logging
from typing import Any, Optional

import litellm
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.core.llm_factory import get_model_string
from app.db import crud
from app.schemas.llm_profile import LLMProfileInternal

logger = logging.getLogger(__name__)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response schemas
# ─────────────────────────────────────────────────────────────────────────────


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    llm_profile_id: Optional[int] = None
    system_prompt: Optional[str] = None


class ProfileSummary(BaseModel):
    id: int
    name: str
    provider: str
    model: str
    is_default: bool


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_profile(
    db: Session,
    llm_profile_id: Optional[int],
) -> LLMProfileInternal:
    """
    Resolve an LLMProfileInternal from either an explicit ID or the default.
    Raises HTTP 400 / 404 on failure.
    """
    if llm_profile_id is not None:
        orm_profile = crud.get_llm_profile(db, llm_profile_id)
        if orm_profile is None:
            raise HTTPException(
                status_code=404,
                detail=f"LLM profile with id={llm_profile_id} not found.",
            )
    else:
        orm_profile = crud.get_default_llm_profile(db)
        if orm_profile is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No default LLM profile is configured. "
                    "Please set a default profile in Admin → LLM Profiles, "
                    "or pass an explicit 'llm_profile_id' in the request body."
                ),
            )

    return LLMProfileInternal.model_validate(orm_profile)


# Providers that work without an API key (local inference)
_NO_KEY_PROVIDERS = {"ollama", "lm_studio"}


def _normalize_ollama_base_url(base_url: str) -> str:
    """
    Ollama's native API lives at the root (e.g. http://localhost:11434).
    litellm always appends /api/chat to whatever base_url it receives, so if
    the stored profile URL ends with /v1 (a common OpenAI-compat convention)
    the resulting URL becomes …/v1/api/chat which Ollama rejects with 405.
    Strip a trailing /v1 so litellm always constructs the correct path.
    """
    url = base_url.rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    return url


def _build_litellm_kwargs(
    internal: LLMProfileInternal,
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    """Build the kwargs dict for litellm.completion."""
    provider_val: str = (
        internal.provider.value
        if hasattr(internal.provider, "value")
        else str(internal.provider)
    )
    model_string = get_model_string(provider_val, internal.model)

    kwargs: dict[str, Any] = {
        "model": model_string,
        "messages": messages,
        "stream": True,
    }

    # API key – skip for local providers that don't need one (e.g. Ollama)
    if internal.api_key and provider_val not in _NO_KEY_PROVIDERS:
        kwargs["api_key"] = internal.api_key

    # Base URL handling
    base_url = internal.base_url
    if provider_val == "ollama":
        # Normalise away any /v1 suffix so litellm builds the correct
        # native-API URL: {base_url}/api/chat
        if base_url:
            base_url = _normalize_ollama_base_url(base_url)
        else:
            base_url = "http://localhost:11434"
    if base_url:
        kwargs["base_url"] = base_url

    if internal.temperature is not None:
        kwargs["temperature"] = internal.temperature
    if internal.max_tokens:
        kwargs["max_tokens"] = internal.max_tokens

    return kwargs


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/chat/send", summary="Stream a chat response via SSE")
def chat_send(
    body: ChatRequest,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """
    Send a list of messages to the configured LLM and stream the response
    back as Server-Sent Events.

    **SSE event format:**
    - `data: {"type": "chunk", "content": "<text>"}`
    - `data: {"type": "done"}`
    - `data: {"type": "error", "message": "<error text>"}`
    """
    internal = _resolve_profile(db, body.llm_profile_id)

    # Build message list, injecting system_prompt at the front if provided
    messages: list[dict[str, str]] = []
    if body.system_prompt:
        messages.append({"role": "system", "content": body.system_prompt})
    messages.extend({"role": m.role, "content": m.content} for m in body.messages)

    kwargs = _build_litellm_kwargs(internal, messages)

    def event_stream():
        try:
            response = litellm.completion(**kwargs)
            for chunk in response:
                try:
                    delta = chunk.choices[0].delta  # type: ignore[union-attr]
                    if delta.content:
                        data = json.dumps({"type": "chunk", "content": delta.content})
                        yield f"data: {data}\n\n"
                except (IndexError, AttributeError):
                    # Malformed chunk – skip silently
                    continue

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as exc:
            logger.exception("Error during LLM streaming: %s", exc)
            error_data = json.dumps({"type": "error", "message": str(exc)})
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )


@router.get(
    "/chat/profiles",
    response_model=list[ProfileSummary],
    summary="List available LLM profiles",
)
def list_chat_profiles(
    db: Session = Depends(get_db),
) -> list[ProfileSummary]:
    """
    Returns a lightweight summary of all configured LLM profiles.
    Useful for populating a profile picker in the chat UI.
    """
    items, _ = crud.get_all_llm_profiles(db)
    return [
        ProfileSummary(
            id=p.id,
            name=p.name,
            provider=p.provider,
            model=p.model,
            is_default=p.is_default,
        )
        for p in items
    ]
