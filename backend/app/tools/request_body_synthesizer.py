"""
tools/request_body_synthesizer.py
─────────────────────────────────
Deterministic Layer-1 request-body resolver for the ``automation-testing-api``
pipeline.

Problem it solves
=================
A Format-B MD spec (contract §3.2) carries a JSON *example* body. Authors
frequently write that example in **schema-placeholder** form —
``{"date": "YYYY-MM-DD", "start_time": "HH:mm", "title": "string"}`` — rather
than with real values. The previous body builder copied the example verbatim,
so the executed request shipped the literal strings ``"YYYY-MM-DD"`` /
``"HH:mm"`` / ``"string"`` and the backend rejected an otherwise-valid
happy-path call.

This module detects placeholder tokens — type names, common date/time format
templates, ``<angle>`` markers, and ``"type (rules…)"`` descriptors — and
replaces ONLY those with format-appropriate valid values, leaving real example
values (``"08:00"``, ``false``, ``"Làm bài tập"``) untouched. It then fills any
declared field the example omits by sampling its type, so the result always
carries every required field with a value the server can actually bind.

The module is rule-based and deterministic — it never calls an LLM. An optional
LLM refinement layer (``crews/request_body_synthesizer_crew.py``) overlays its
output in the adaptive planner.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.tools.md_api_spec_validator import ParsedField, ParsedRequest

# Concrete, deterministic sample value per declared type. Kept aligned with the
# generator so type-sampled and placeholder-resolved fields agree.
_TYPE_SAMPLE: dict[str, Any] = {
    "string": "sample", "str": "sample", "text": "sample", "any": "sample",
    "int": 1, "integer": 1, "uint": 1, "long": 1,
    "float": 1.5, "number": 1.5, "double": 1.5,
    "bool": True, "boolean": True,
    "date": "2026-01-25",
    "datetime": "2026-01-25T08:00:00Z", "timestamp": "2026-01-25T08:00:00Z",
    "time": "08:00",
    "email": "user@example.com",
    "uuid": "00000000-0000-4000-8000-000000000000",
    "guid": "00000000-0000-4000-8000-000000000000",
    "url": "https://example.com",
    "object": {}, "json": {}, "array": [],
}

# Type names whose generic sample should defer to a field-name hint when one
# exists (e.g. a ``string`` field called ``email`` → an email value).
_STRINGY = {"string", "str", "text", "any"}

# Date/time FORMAT templates an author may write as the placeholder value.
# Keys are normalised to lowercase; the full value must equal one of these.
_FORMAT_MAP: dict[str, str] = {
    "yyyy-mm-dd": "2026-01-25",
    "yyyy/mm/dd": "2026/01/25",
    "dd-mm-yyyy": "25-01-2026",
    "dd/mm/yyyy": "25/01/2026",
    "mm/dd/yyyy": "01/25/2026",
    "yyyy-mm-ddthh:mm:ssz": "2026-01-25T08:00:00Z",
    "yyyy-mm-ddthh:mm:ss": "2026-01-25T08:00:00",
    "yyyy-mm-dd hh:mm:ss": "2026-01-25 08:00:00",
    "yyyy-mm-dd hh:mm": "2026-01-25 08:00",
    "hh:mm:ss": "08:00:00",
    "hh:mm": "08:00",
    "yyyy-mm": "2026-01",
    "yyyy": "2026",
}

_RE_TYPE_HEAD = re.compile(r"^([a-z]+)\s*[\(\[]")
_RE_LEN_RANGE = re.compile(r"(\d+)\s*(?:-|–|to)\s*(\d+)")
_RE_LEN_MIN = re.compile(r"min(?:imum)?\s*(\d+)")


def resolve_request_body(request: ParsedRequest) -> dict[str, Any]:
    """Build a representative request body with placeholder values resolved.

    Two spec formats are supported (contract §3.2):
      * Format B — a JSON example block (``raw_body_schema``): every value is
        passed through :func:`_resolve_value`, which replaces schema-placeholder
        tokens with valid values and keeps real example values verbatim.
      * Format A — a markdown field table (``body_fields``): each declared field
        the example omits is sampled by its type (honouring length ``rules``).

    Args:
        request: The :class:`ParsedRequest` from the MD spec validator.

    Returns:
        A ``dict`` body where every value is a value the target API can bind.
    """
    body: dict[str, Any] = {}

    example = _parse_json(request.raw_body_schema)
    if isinstance(example, dict):
        for key, value in example.items():
            body[key] = _resolve_value(value, key)

    for field in request.body_fields:
        if field.name not in body:
            body[field.name] = _sample_for_field(field)

    return body


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _parse_json(raw: str) -> Any:
    """Parse a raw JSON body example into a Python object, or ``None`` on failure."""
    if not raw or not raw.strip():
        return None
    import json

    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _resolve_value(value: Any, field_name: str) -> Any:
    """Recursively resolve placeholders inside an example value.

    Non-string scalars (``int`` / ``float`` / ``bool`` / ``None``) are real
    example data and pass through untouched; only strings can be placeholders.
    """
    if isinstance(value, dict):
        return {k: _resolve_value(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_value(item, field_name) for item in value]
    if isinstance(value, str):
        return _resolve_string(value, field_name)
    return value


def _resolve_string(text: str, field_name: str) -> Any:
    """Resolve a single string: a placeholder token → a valid value, else verbatim."""
    raw = text.strip()
    if not raw:
        return text

    # ``<string>`` / ``<YYYY-MM-DD>`` angle markers are always placeholders;
    # fall back to a field hint or generic string when the inner token is opaque.
    if raw.startswith("<") and raw.endswith(">") and len(raw) > 2:
        inner = raw[1:-1].strip()
        known = _resolve_known(inner, field_name)
        return known if known is not None else (
            _hint_for_field(field_name) or _TYPE_SAMPLE["string"]
        )

    known = _resolve_known(raw, field_name)
    return known if known is not None else text


def _resolve_known(raw: str, field_name: str) -> Optional[Any]:
    """Return a valid value when *raw* is a recognised placeholder, else ``None``."""
    key = raw.lower()
    if key in _FORMAT_MAP:
        return _FORMAT_MAP[key]

    ptype = _placeholder_type(raw)
    if ptype is None:
        return None
    if ptype in _STRINGY:
        return _hint_for_field(field_name) or _type_value(ptype)
    return _type_value(ptype)


def _placeholder_type(raw: str) -> Optional[str]:
    """Detect a bare type name (``"string"``) or a ``"string (rules…)"`` descriptor."""
    key = raw.lower().strip()
    if key in _TYPE_SAMPLE:
        return key
    head = _RE_TYPE_HEAD.match(key)
    if head and head.group(1) in _TYPE_SAMPLE:
        return head.group(1)
    return None


def _type_value(ptype: str) -> Any:
    """Sample value for a type, returning fresh containers for object/array."""
    if ptype in ("object", "json"):
        return {}
    if ptype == "array":
        return []
    return _TYPE_SAMPLE[ptype]


def _hint_for_field(field_name: str) -> Optional[str]:
    """Field-name-aware sample for an otherwise generic ``string`` placeholder."""
    name = (field_name or "").lower()
    if "email" in name:
        return "user@example.com"
    if name.endswith("_at") or "datetime" in name or "timestamp" in name:
        return _TYPE_SAMPLE["datetime"]
    if "date" in name:
        return _TYPE_SAMPLE["date"]
    if "time" in name:
        return _TYPE_SAMPLE["time"]
    if "url" in name or "link" in name:
        return "https://example.com"
    if "phone" in name or "mobile" in name:
        return "+84901234567"
    if "password" in name:
        return "Password123!"
    if "title" in name or "name" in name:
        return "Sample text"
    return None


def _sample_for_field(field: ParsedField) -> Any:
    """Sample a value for a declared field absent from the JSON example."""
    ftype = (field.type or "").lower().strip()
    if ftype in _TYPE_SAMPLE:
        value: Any = (
            _hint_for_field(field.name) or _type_value(ftype)
            if ftype in _STRINGY else _type_value(ftype)
        )
    else:
        value = _hint_for_field(field.name) or "sample"

    if isinstance(value, str) and field.rules:
        value = _apply_length_rules(value, field.rules)
    return value


def _apply_length_rules(value: str, rules: str) -> str:
    """Grow *value* to satisfy a ``min N`` / ``N-M chars`` length rule (best effort)."""
    rule = rules.lower()
    target: Optional[int] = None
    m_range = _RE_LEN_RANGE.search(rule)
    m_min = _RE_LEN_MIN.search(rule)
    if m_range:
        target = int(m_range.group(1))
    elif m_min:
        target = int(m_min.group(1))
    if target and len(value) < target:
        value = (value * (target // len(value) + 1))[:target]
    return value
