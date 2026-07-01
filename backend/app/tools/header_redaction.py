"""
tools/header_redaction.py
───────────────────────────
Defence-in-depth redaction of secret HTTP header values.

By contract the MD spec never carries literal credential values — required
headers are names/schema only and planners must emit placeholders like
``${TOKEN}``. This helper masks any *literal-looking* value on a known-sensitive
header so a contract violation can never leak a real secret into a MongoDB
snapshot, a progress event, a log line, or an exported HTML/PDF/DOCX report.

Placeholders (``${...}``), empty values, and already-redacted values are left
untouched so legitimate, secret-free test data still renders.
"""

from __future__ import annotations

import re
from typing import Any

_REDACTED = "***REDACTED***"

# Header names whose value is treated as a secret (compared case-insensitively).
_SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "api-key",
        "apikey",
        "x-auth-token",
        "x-access-token",
        "x-secret",
        "x-amz-security-token",
    }
)

# A placeholder *token* (e.g. ${TOKEN}, {{api_key}}, <token>, $token). Matched
# as a SUBSTRING so idiomatic auth values like ``Bearer ${TOKEN}`` or
# ``Token ${X}`` are recognised as templated (not raw secrets) and preserved —
# otherwise the redacted value would be sent literally and break auth cases.
_PLACEHOLDER_TOKEN_RE = re.compile(
    r"\$\{[^}]*\}|\{\{[^}]*\}\}|<[^>]+>|\$[A-Za-z0-9_]+"
)


def _is_placeholder(value: str) -> bool:
    """True when *value* carries no literal secret (empty, already redacted, or
    contains a templating placeholder token)."""
    stripped = value.strip()
    return (
        stripped == ""
        or stripped == _REDACTED
        or bool(_PLACEHOLDER_TOKEN_RE.search(stripped))
    )


def redact_headers(headers: Any) -> Any:
    """Return a copy of *headers* with secret values on sensitive headers masked.

    Non-dict input is returned unchanged so callers can pass through optional
    ``request_headers`` values safely.
    """
    if not isinstance(headers, dict):
        return headers
    redacted: dict[str, Any] = {}
    for key, value in headers.items():
        if str(key).lower() in _SENSITIVE_HEADERS and not _is_placeholder(str(value)):
            redacted[key] = _REDACTED
        else:
            redacted[key] = value
    return redacted


def redact_case(case: Any) -> Any:
    """Redact ``request_headers`` on a single test-case dict (copy-on-write)."""
    if not isinstance(case, dict) or "request_headers" not in case:
        return case
    if not isinstance(case.get("request_headers"), dict):
        return case
    return {**case, "request_headers": redact_headers(case["request_headers"])}


def redact_cases(cases: Any) -> list[Any]:
    """Redact headers across a list of test-case dicts."""
    if not isinstance(cases, list):
        return cases
    return [redact_case(c) for c in cases]
