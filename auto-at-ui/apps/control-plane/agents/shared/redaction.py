"""Redact untrusted evidence before it enters prompts, proposals, or audit logs."""

from collections.abc import Mapping
from re import IGNORECASE
from re import compile as compile_pattern
from urllib.parse import parse_qsl, urlencode

REDACTED = "[REDACTED]"
REDACTED_LOG_ASSIGNMENT = compile_pattern(
    r"(?<![?&])\b(authorization|cookie|password|secret|token|api[_-]?key|session)\s*[:=]\s*[^\s,;]+",
    IGNORECASE,
)
SENSITIVE_FIELD_NAMES = frozenset(
    {
        "authorization",
        "cookie",
        "password",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "client_secret",
        "set-cookie",
        "session",
    }
)


def redact_mapping(values: Mapping[str, object]) -> dict[str, object]:
    """Recursively redact secret-bearing mappings before data crosses an agent boundary."""
    return {
        key: REDACTED if key.lower() in SENSITIVE_FIELD_NAMES else redact_value(value)
        for key, value in values.items()
    }


def redact_value(value: object) -> object:
    """Return a redacted copy of evidence without mutating its input."""
    if isinstance(value, Mapping):
        return redact_mapping(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    if isinstance(value, str):
        return _redact_log_assignments(_redact_url_query(value))
    return value


def _redact_url_query(value: str) -> str:
    """Redact every query value; URLs and request-target log lines may carry PII."""
    prefix, separator, query = value.partition("?")
    if not separator:
        return value

    fragment = ""
    if "#" in query:
        query, fragment = query.split("#", maxsplit=1)
        fragment = f"#{fragment}"

    parameters = parse_qsl(query, keep_blank_values=True)
    if not parameters:
        return value

    redacted_query = urlencode([(key, REDACTED) for key, _ in parameters])
    return f"{prefix}?{redacted_query}{fragment}"


def _redact_log_assignments(value: str) -> str:
    return REDACTED_LOG_ASSIGNMENT.sub(lambda match: f"{match.group(1)}={REDACTED}", value)
