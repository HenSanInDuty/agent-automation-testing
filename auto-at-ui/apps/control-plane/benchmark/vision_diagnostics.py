"""Safe diagnostics for Hugging Face multimodal endpoint compatibility."""

from collections.abc import Awaitable, Callable

_ERROR_CATEGORIES = (
    "image", "url", "provider", "model", "format", "auth", "unsupported",
    "content", "parameter", "permission", "credit", "quota", "invalid",
    "request", "rate", "timeout",
)


async def classify_vision_transport(
    invoke: Callable[[], Awaitable[object]],
) -> dict[str, object]:
    """Return exception type/categories without retaining provider response text."""
    try:
        await invoke()
    except Exception as error:
        response = getattr(error, "response", None)
        message = _safe_error_text(error).lower()
        categories = [
            category
            for category in _ERROR_CATEGORIES
            if category in message
        ]
        return {
            "result": "failed",
            "exception_type": type(error).__name__,
            "http_status": getattr(response, "status_code", None),
            "categories": categories,
        }
    return {"result": "completed"}


def _safe_error_text(error: Exception) -> str:
    """Extract error text only long enough to classify it; never return it."""
    response = getattr(error, "response", None)
    if response is None:
        return str(error)
    try:
        body = response.json()
    except (TypeError, ValueError):
        return str(error)
    return " ".join(_strings(body))


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []


async def exercise_temporary_image_store(store, *, tenant_id: str, session_id, image: bytes):
    """Confirm upload/sign/delete without returning the signed URL."""
    try:
        async with store.deliver(
            tenant_id=tenant_id, session_id=session_id, sequence=1, image=image
        ) as signed_url:
            return {"result": "completed", "https_url": signed_url.startswith("https://")}
    except Exception as error:
        response = getattr(error, "response", None)
        return {
            "result": "failed",
            "exception_type": type(error).__name__,
            "http_status": getattr(response, "status_code", None),
        }
