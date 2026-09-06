"""Safe, bounded handoff data for privileged Vision diagnostics.

This module deliberately retains no provider exception text or arbitrary response
objects.  Later persistence code may encrypt its output, but ordinary flows only
use the stable failure code.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from re import compile


class VisualDiagnosticCode(StrEnum):
    PROVIDER_TRANSPORT = "provider_transport"
    PROVIDER_HTTP = "provider_http"
    RESPONSE_NOT_OBJECT = "response_not_object"
    RESPONSE_MISSING_CHOICES = "response_missing_choices"
    RESPONSE_MISSING_CONTENT = "response_missing_content"
    INVALID_JSON = "invalid_json"
    INVALID_ROOT_SHAPE = "invalid_root_shape"
    INVALID_CANDIDATE_SCHEMA = "invalid_candidate_schema"
    EMPTY_CANDIDATES = "empty_candidates"
    CANDIDATE_LIMIT_EXCEEDED = "candidate_limit_exceeded"
    REDACTION_FAILED = "redaction_failed"
    PAYLOAD_TOO_LARGE = "payload_too_large"


class VisualDiagnosticFailure(ValueError):
    """An allow-listed diagnostic classification with internal exception chaining."""

    def __init__(
        self,
        code: VisualDiagnosticCode,
        *,
        provider_status: int | None = None,
        provider_category: str | None = None,
    ) -> None:
        self.code = code
        self.provider_status = provider_status
        self.provider_category = provider_category
        super().__init__(code.value)


_SECRET_PATTERNS = (
    compile(r"(?i)(?:bearer\s+)[a-z0-9._~+/-]+=*"),
    compile(r"(?i)(?:api[_-]?key|password|secret|token)\s*[:=]\s*[^\s,;]+"),
    compile(r"(?i)(?:set-cookie|cookie)\s*[:=]\s*[^\r\n]+"),
    # Returned model text can echo a temporary image URL. Evidence must never
    # retain Drive links or any other remotely retrievable URL.
    compile(r"(?i)https?://[^\s<>\"']+"),
)
_MAX_CAPTURE_BYTES = 16_384
_ALLOWED_PROVIDER_CATEGORIES = frozenset({"http", "transport", "timeout", "unknown"})


@dataclass(frozen=True)
class VisualDiagnosticCapture:
    """Text-only candidate payload, normalized before the encryption boundary."""

    content: str | None
    content_sha256: str | None
    provider_status: int | None
    provider_category: str | None

    @classmethod
    def from_content(
        cls,
        content: str | None,
        *,
        provider_status: int | None = None,
        provider_category: str | None = None,
    ) -> VisualDiagnosticCapture:
        if content is not None and not isinstance(content, str):
            raise VisualDiagnosticFailure(VisualDiagnosticCode.REDACTION_FAILED)
        if provider_status is not None and (
            not isinstance(provider_status, int) or provider_status < 100
        ):
            raise VisualDiagnosticFailure(VisualDiagnosticCode.REDACTION_FAILED)
        if provider_category is not None and provider_category not in _ALLOWED_PROVIDER_CATEGORIES:
            raise VisualDiagnosticFailure(VisualDiagnosticCode.REDACTION_FAILED)
        if content is None:
            return cls(None, None, provider_status, provider_category)
        try:
            redacted = content
            for pattern in _SECRET_PATTERNS:
                redacted = pattern.sub("[REDACTED]", redacted)
            encoded = redacted.encode("utf-8")
        except (TypeError, UnicodeError) as error:
            raise VisualDiagnosticFailure(VisualDiagnosticCode.REDACTION_FAILED) from error
        if len(encoded) > _MAX_CAPTURE_BYTES:
            raise VisualDiagnosticFailure(VisualDiagnosticCode.PAYLOAD_TOO_LARGE)
        return cls(redacted, sha256(encoded).hexdigest(), provider_status, provider_category)
