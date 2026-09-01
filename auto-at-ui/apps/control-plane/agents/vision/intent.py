"""Bounded encrypted retention for a visual request's original intent."""

from datetime import UTC, datetime

from cryptography.fernet import Fernet, InvalidToken


class VisualIntentUnavailableError(ValueError):
    """The original request is unavailable, expired, or cannot be authenticated."""


def encrypt_visual_intent(intent: str, key: str | None) -> str:
    if not key:
        raise VisualIntentUnavailableError("vision request encryption is not configured")
    try:
        return Fernet(key.encode("ascii")).encrypt(intent.encode("utf-8")).decode("ascii")
    except (UnicodeEncodeError, ValueError) as error:
        raise VisualIntentUnavailableError("vision request encryption is not configured") from error


def decrypt_visual_intent(
    encrypted: str, key: str | None, retention_until: datetime
) -> str:
    if retention_until <= datetime.now(UTC):
        raise VisualIntentUnavailableError("visual request retention has expired")
    if not key:
        raise VisualIntentUnavailableError("vision request encryption is not configured")
    try:
        return Fernet(key.encode("ascii")).decrypt(encrypted.encode("ascii")).decode("utf-8")
    except (UnicodeEncodeError, InvalidToken, ValueError, UnicodeDecodeError) as error:
        raise VisualIntentUnavailableError("visual request is unavailable") from error
