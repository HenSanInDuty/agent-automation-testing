"""Encrypt bounded, redacted Vision diagnostics at the persistence boundary."""

from __future__ import annotations

from dataclasses import dataclass
from re import fullmatch

from cryptography.fernet import Fernet, InvalidToken

from agents.vision.diagnostics import VisualDiagnosticCapture


class DebugEvidenceUnavailableError(ValueError):
    """Keys, ciphertext, or input are unavailable; no detail is safe to expose."""


@dataclass(frozen=True)
class EncryptedDebugEvidence:
    ciphertext: str
    key_id: str
    checksum: str | None
    byte_count: int
    redaction_version: str = "vision-debug-redaction-v1"


def encrypt_debug_evidence(
    capture: VisualDiagnosticCapture, *, key: str | None, key_id: str | None
) -> EncryptedDebugEvidence:
    if not key or not key_id or fullmatch(r"[A-Za-z0-9._-]{1,100}", key_id) is None:
        raise DebugEvidenceUnavailableError("debug evidence is unavailable")
    payload = (capture.content or "").encode("utf-8")
    try:
        ciphertext = Fernet(key.encode("ascii")).encrypt(payload).decode("ascii")
    except (UnicodeEncodeError, ValueError) as error:
        raise DebugEvidenceUnavailableError("debug evidence is unavailable") from error
    return EncryptedDebugEvidence(ciphertext, key_id, capture.content_sha256, len(payload))


def decrypt_debug_evidence(
    evidence: EncryptedDebugEvidence,
    *,
    key: str | None,
    key_id: str | None,
    previous_key: str | None = None,
    previous_key_id: str | None = None,
) -> str:
    if evidence.key_id == key_id:
        selected_key = key
    elif evidence.key_id == previous_key_id:
        selected_key = previous_key
    else:
        selected_key = None
    if not selected_key:
        raise DebugEvidenceUnavailableError("debug evidence is unavailable")
    try:
        return (
            Fernet(selected_key.encode("ascii"))
            .decrypt(evidence.ciphertext.encode("ascii"))
            .decode("utf-8")
        )
    except (UnicodeEncodeError, InvalidToken, ValueError, UnicodeDecodeError) as error:
        raise DebugEvidenceUnavailableError("debug evidence is unavailable") from error
