"""
tools/md_api_spec_validator.py
──────────────────────────────
Pure-Python validator for the Automation Testing API MD spec contract.

See ``docs/Flow/automation-testing-api-md-contract.md`` (v1) for the rules.

Public API:
    validate_md_api_spec(text, strict=True) -> ValidationResult
        Validates an MD API spec string. When ``strict=True`` and any
        contract violation is detected, the result's ``valid=False`` and
        the caller is expected to raise :class:`MDSpecValidationError`.

    ValidationResult                — Pydantic model with parsed sections.
    ParsedEndpoint / ParsedRequest /
    ParsedResponse                  — structured representation of the spec
                                      that downstream nodes can consume.

The module is rule-based (no LLM) and deterministic.
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field

# ─────────────────────────────────────────────────────────────────────────────
# Constants — contract v1
# ─────────────────────────────────────────────────────────────────────────────

# Heading synonyms (case-insensitive). Canonical key → list of accepted variants.
_SECTION_SYNONYMS: dict[str, list[str]] = {
    "endpoint": ["endpoint", "api endpoint", "api", "route", "uri"],
    "request": ["request", "req", "request payload", "input", "body"],
    "response": ["response", "responses", "resp", "output", "result"],
    "headers": ["headers", "request headers", "header"],
}

_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}

# Methods that require a Request body section.
_METHODS_WITH_BODY = {"POST", "PUT", "PATCH"}

_RE_METHOD = re.compile(r"(?im)^\s*[-*]?\s*Method\s*[:=]\s*(\w+)")
_RE_PATH = re.compile(r"(?im)^\s*[-*]?\s*Path\s*[:=]\s*(\S+)")
_RE_AUTH = re.compile(r"(?im)^\s*[-*]?\s*Auth\s*[:=]\s*(.+)$")
_RE_BASE_URL = re.compile(r"(?im)^\s*[-*]?\s*Base[\s_-]*URL\s*[:=]\s*(\S+)")
_RE_STATUS_CODE = re.compile(r"\b([1-5]\d{2})\b")
_RE_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*[:\- ]+\s*\|")


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic output models
# ─────────────────────────────────────────────────────────────────────────────


class ParsedField(BaseModel):
    name: str
    type: str = ""
    required: bool = False
    rules: str = ""


class ParsedEndpoint(BaseModel):
    method: str = ""
    path: str = ""
    auth: str = ""


class ParsedRequest(BaseModel):
    content_type: str = ""
    body_fields: list[ParsedField] = Field(default_factory=list)
    raw_body_schema: str = ""


class ParsedResponse(BaseModel):
    status_code: int
    description: str = ""
    payload_preview: str = ""


class ParsedHeader(BaseModel):
    name: str
    value_schema: str = ""
    required: bool = False


class ParsedSpec(BaseModel):
    base_url: str = ""
    endpoint: ParsedEndpoint = Field(default_factory=ParsedEndpoint)
    request: ParsedRequest = Field(default_factory=ParsedRequest)
    responses: list[ParsedResponse] = Field(default_factory=list)
    response_body: str = ""
    headers: list[ParsedHeader] = Field(default_factory=list)


class FieldViolation(BaseModel):
    field: str
    code: str
    detail: str


class ValidationResult(BaseModel):
    valid: bool
    code: str = ""
    detail: str = ""
    missing_sections: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    field_errors: list[FieldViolation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    parsed: ParsedSpec = Field(default_factory=ParsedSpec)


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────


def validate_md_api_spec(
    text: str,
    *,
    strict: bool = True,
    extra_synonyms: Optional[dict[str, list[str]]] = None,
) -> ValidationResult:
    """Validate an MD API spec against contract v1.

    Args:
        text:            Raw markdown content of the uploaded spec file.
        strict:          When True (default) the function returns ``valid=False``
                         and the caller raises :class:`MDSpecValidationError`.
                         When False all errors are converted to warnings and
                         ``valid=True`` is returned so downstream nodes can run.
        extra_synonyms:  Optional mapping that extends ``_SECTION_SYNONYMS``
                         at runtime — e.g. for Vietnamese headings.

    Returns:
        :class:`ValidationResult` with ``parsed`` populated when sections
        could be located, even if the spec is invalid.
    """
    synonyms = _merge_synonyms(extra_synonyms)
    sections = _extract_sections(text, synonyms)
    parsed = ParsedSpec(base_url=_parse_base_url(text))
    violations: list[FieldViolation] = []
    missing_sections: list[str] = []

    # ── 1. Endpoint section ────────────────────────────────────────────────
    endpoint_text = sections.get("endpoint", "")
    if not endpoint_text:
        missing_sections.append("endpoint")
        violations.extend(
            [
                _violation("endpoint.method", "MD_SPEC_MISSING_ENDPOINT", "Endpoint method is required."),
                _violation("endpoint.path", "MD_SPEC_MISSING_ENDPOINT", "Endpoint path is required."),
            ]
        )
    else:
        endpoint, ep_missing = _parse_endpoint(endpoint_text)
        parsed.endpoint = endpoint
        for field in ep_missing:
            canonical = f"endpoint.{field.lower()}"
            violations.append(
                _violation(canonical, "MD_SPEC_MISSING_ENDPOINT", f"{canonical} is required.")
            )
        if endpoint.method and endpoint.method.upper() not in _HTTP_METHODS:
            violations.append(
                _violation(
                    "endpoint.method",
                    "MD_SPEC_INVALID_METHOD",
                    f"Endpoint method must be one of {sorted(_HTTP_METHODS)}.",
                )
            )
        if endpoint.path and not endpoint.path.startswith("/"):
            violations.append(
                _violation("endpoint.path", "MD_SPEC_INVALID_PATH", "Endpoint path must start with '/'.")
            )

    # ── 2. Request section ─────────────────────────────────────────────────
    request_text = sections.get("request", "")
    if not request_text:
        missing_sections.append("request")
        violations.append(
            _violation("request.body", "MD_SPEC_MISSING_REQUEST_BODY", "A non-empty request body schema is required for every method.")
        )
    else:
        req, req_missing = _parse_request(request_text)
        parsed.request = req
        if not req.body_fields and not req.raw_body_schema:
            violations.append(
                _violation("request.body", "MD_SPEC_MISSING_REQUEST_BODY", "Request body schema must contain fields or a JSON block.")
            )

    # ── 3. Response section ────────────────────────────────────────────────
    response_text = sections.get("response", "")
    if not response_text:
        missing_sections.append("response")
        violations.extend(
            [
                _violation("response.status", "MD_SPEC_MISSING_RESPONSE_STATUS", "At least one response status is required."),
                _violation("response.body", "MD_SPEC_MISSING_RESPONSE_BODY", "A non-empty response body schema is required."),
            ]
        )
    else:
        parsed.responses = _parse_responses(response_text)
        parsed.response_body = _extract_response_body(response_text, parsed.responses)
        if not parsed.responses:
            violations.append(
                _violation("response.status", "MD_SPEC_MISSING_RESPONSE_STATUS", "Response section must contain an HTTP status code.")
            )
        if not parsed.response_body:
            violations.append(
                _violation("response.body", "MD_SPEC_MISSING_RESPONSE_BODY", "Response section must contain a JSON body or schema.")
            )

    if not parsed.base_url or not _is_valid_base_url(parsed.base_url):
        code = "MD_SPEC_MISSING_BASE_URL" if not parsed.base_url else "MD_SPEC_INVALID_BASE_URL"
        violations.append(
            _violation("base_url", code, "Base URL must be an absolute http(s) URL.")
        )

    headers_text = sections.get("headers", "")
    parsed.headers, header_conflicts = _parse_headers(headers_text)
    if not headers_text:
        missing_sections.append("headers")
    if not parsed.headers:
        violations.append(
            _violation("headers", "MD_SPEC_MISSING_HEADERS", "Declare at least one request header name or schema; secret values belong in runtime credentials.")
        )
    for header_name in header_conflicts:
        violations.append(
            _violation(
                f"headers.{header_name.lower()}",
                "MD_SPEC_CONFLICTING_HEADER",
                f"Header {header_name!r} is declared more than once with conflicting schema metadata.",
            )
        )

    return _result_from_violations(
        parsed=parsed,
        violations=violations,
        missing_sections=missing_sections,
        strict=strict,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _merge_synonyms(
    extra: Optional[dict[str, list[str]]],
) -> dict[str, list[str]]:
    if not extra:
        return _SECTION_SYNONYMS
    merged: dict[str, list[str]] = {}
    for key, defaults in _SECTION_SYNONYMS.items():
        merged[key] = list(defaults) + [s.lower() for s in extra.get(key, [])]
    return merged


def _violation(field: str, code: str, detail: str) -> FieldViolation:
    return FieldViolation(field=field, code=code, detail=detail)


def _result_from_violations(
    *,
    parsed: ParsedSpec,
    violations: list[FieldViolation],
    missing_sections: list[str],
    strict: bool,
) -> ValidationResult:
    if not violations:
        return ValidationResult(valid=True, parsed=parsed)

    warnings = [f"[{item.code}] {item.field}: {item.detail}" for item in violations]
    missing_fields = list(dict.fromkeys(item.field for item in violations))
    first = violations[0]
    detail = "API specification contract violations: " + "; ".join(
        f"{item.field} ({item.code})" for item in violations
    )
    return ValidationResult(
        valid=not strict,
        code=first.code if strict else "",
        detail=detail if strict else "",
        missing_sections=list(dict.fromkeys(missing_sections)),
        missing_fields=missing_fields,
        field_errors=violations,
        warnings=warnings if not strict else [],
        parsed=parsed,
    )


def _parse_base_url(text: str) -> str:
    match = _RE_BASE_URL.search(text or "")
    if not match:
        return ""
    return match.group(1).strip().strip("`").rstrip(".,;:")


def _is_valid_base_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _extract_sections(
    text: str,
    synonyms: dict[str, list[str]],
) -> dict[str, str]:
    """Split *text* by H2/H3 headings, return canonical_key → body."""
    # Compile a reverse map: alias_lower → canonical_key
    alias_to_canonical: dict[str, str] = {}
    for canonical, aliases in synonyms.items():
        for alias in aliases:
            alias_to_canonical[alias.lower().strip()] = canonical

    # Match H2 and H3 headings (## or ###)
    heading_re = re.compile(r"(?m)^(#{2,3})\s+(.+?)\s*$")
    matches = list(heading_re.finditer(text))
    sections: dict[str, str] = {}

    for idx, m in enumerate(matches):
        title_raw = m.group(2).strip()
        # Strip "API: <name>" prefix or trailing punctuation
        title_clean = re.sub(r"^api\s*[:\-]\s*", "", title_raw, flags=re.IGNORECASE)
        title_clean = title_clean.strip().rstrip(":")
        canonical = alias_to_canonical.get(title_clean.lower())
        if canonical is None:
            continue

        body_start = m.end()
        body_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()

        # Multi-endpoint: only record the FIRST occurrence per canonical section.
        # The full multi-endpoint mode can be re-enabled when downstream nodes
        # support array specs (out of scope for v1).
        if canonical not in sections:
            sections[canonical] = body

    return sections


def _parse_endpoint(text: str) -> tuple[ParsedEndpoint, list[str]]:
    ep = ParsedEndpoint()
    missing: list[str] = []

    m_method = _RE_METHOD.search(text)
    if m_method:
        ep.method = m_method.group(1).strip().upper()
    else:
        missing.append("Method")

    m_path = _RE_PATH.search(text)
    if m_path:
        ep.path = m_path.group(1).strip()
    else:
        missing.append("Path")

    m_auth = _RE_AUTH.search(text)
    if m_auth:
        ep.auth = m_auth.group(1).strip()

    return ep, missing


def _parse_request(text: str) -> tuple[ParsedRequest, list[str]]:
    req = ParsedRequest()
    missing: list[str] = []

    # Content-Type (optional)
    m_ct = re.search(
        r"(?im)^\s*[-*]?\s*Content[\- ]Type\s*[:=]\s*([\w./+\-]+)",
        text,
    )
    if m_ct:
        req.content_type = m_ct.group(1).strip()

    # Try markdown table parse first
    req.body_fields = _parse_markdown_field_table(text)

    # JSON code block fallback
    json_block = _extract_first_code_block(text, lang_hint="json")
    if json_block:
        req.raw_body_schema = json_block

    return req, missing


def _parse_headers(text: str) -> tuple[list[ParsedHeader], list[str]]:
    if not text:
        return [], []

    lines = [line for line in text.splitlines() if line.strip()]
    headers: list[ParsedHeader] = []
    seen: set[str] = set()
    by_name: dict[str, ParsedHeader] = {}
    conflicts: list[str] = []
    table_header_index: Optional[int] = None
    table_columns: dict[str, int] = {}

    for index, line in enumerate(lines):
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.lower() for cell in _split_table_row(line)]
        if any(name in cells for name in ("header", "name")):
            if index + 1 < len(lines) and _RE_TABLE_SEPARATOR.match(lines[index + 1]):
                table_header_index = index
                table_columns = {cell: position for position, cell in enumerate(cells)}
                break

    if table_header_index is not None:
        name_key = "header" if "header" in table_columns else "name"
        for line in lines[table_header_index + 2 :]:
            if not line.lstrip().startswith("|"):
                break
            cells = _split_table_row(line)
            name_index = table_columns[name_key]
            if name_index >= len(cells):
                continue
            name = cells[name_index].strip()
            normalized = name.lower()
            if not name:
                continue
            schema = ""
            for schema_key in ("schema", "type", "description"):
                position = table_columns.get(schema_key)
                if position is not None and position < len(cells):
                    schema = cells[position].strip()
                    break
            required_position = table_columns.get("required")
            required = bool(
                required_position is not None
                and required_position < len(cells)
                and cells[required_position].strip().lower()
                in {"yes", "y", "true", "required"}
            )
            candidate = ParsedHeader(
                name=name,
                value_schema=_safe_header_schema(name, schema),
                required=required,
            )
            existing = by_name.get(normalized)
            if existing:
                if (existing.value_schema, existing.required) != (
                    candidate.value_schema,
                    candidate.required,
                ):
                    conflicts.append(existing.name)
                continue
            headers.append(candidate)
            seen.add(normalized)
            by_name[normalized] = candidate

    if headers:
        return headers, list(dict.fromkeys(conflicts))

    for line in lines:
        match = re.match(r"^\s*[-*]\s*`?([A-Za-z][A-Za-z0-9-]*)`?(?:\s*[:(]|\s*$)", line)
        if not match:
            continue
        name = match.group(1)
        normalized = name.lower()
        if normalized not in seen:
            headers.append(ParsedHeader(name=name))
            seen.add(normalized)
    return headers, []


def _safe_header_schema(name: str, schema: str) -> str:
    normalized = name.lower().replace("_", "-")
    if normalized in {"authorization", "cookie", "set-cookie", "api-key", "x-api-key"}:
        return "runtime credential"
    return schema


def _parse_markdown_field_table(text: str) -> list[ParsedField]:
    """Parse a markdown table with columns: field, type, required, [rules]."""
    lines = [line for line in text.splitlines() if line.strip()]
    fields: list[ParsedField] = []
    header_idx: Optional[int] = None
    col_index: dict[str, int] = {}

    for idx, line in enumerate(lines):
        if line.lstrip().startswith("|"):
            cells = _split_table_row(line)
            cells_lower = [c.lower() for c in cells]
            if any(h in cells_lower for h in ("field", "name", "param")):
                # candidate header — confirm next line is separator
                if idx + 1 < len(lines) and _RE_TABLE_SEPARATOR.match(lines[idx + 1]):
                    header_idx = idx
                    col_index = {c: i for i, c in enumerate(cells_lower)}
                    break

    if header_idx is None:
        return fields

    field_key = (
        "field" if "field" in col_index else ("name" if "name" in col_index else "param")
    )

    for line in lines[header_idx + 2 :]:
        if not line.lstrip().startswith("|"):
            break
        cells = _split_table_row(line)
        if not cells:
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        try:
            name = cells[col_index[field_key]].strip()
        except (KeyError, IndexError):
            continue
        if not name:
            continue
        ftype = ""
        required = False
        rules = ""
        if "type" in col_index and col_index["type"] < len(cells):
            ftype = cells[col_index["type"]].strip()
        if "required" in col_index and col_index["required"] < len(cells):
            required = cells[col_index["required"]].strip().lower() in {
                "yes",
                "y",
                "true",
                "required",
                "✓",
            }
        if "rules" in col_index and col_index["rules"] < len(cells):
            rules = cells[col_index["rules"]].strip()
        fields.append(
            ParsedField(name=name, type=ftype, required=required, rules=rules)
        )

    return fields


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [c.strip() for c in stripped.split("|")]


def _extract_first_code_block(text: str, lang_hint: str = "") -> str:
    pattern = r"```" + (lang_hint or "[a-zA-Z]*") + r"\s*\n([\s\S]*?)\n```"
    m = re.search(pattern, text)
    if m:
        return m.group(1).strip()
    return ""


def _parse_responses(text: str) -> list[ParsedResponse]:
    responses: list[ParsedResponse] = []
    seen: set[int] = set()

    for line in text.splitlines():
        for match in _RE_STATUS_CODE.finditer(line):
            code = int(match.group(1))
            if code in seen:
                continue
            seen.add(code)
            # Description = rest of the line after the code
            tail = line[match.end():].strip()
            tail = tail.lstrip(":-• ").strip()
            payload_preview = ""
            if "{" in tail:
                brace_idx = tail.index("{")
                payload_preview = tail[brace_idx:][:200]
                description = tail[:brace_idx].strip(" :-")
            else:
                description = tail
            responses.append(
                ParsedResponse(
                    status_code=code,
                    description=description[:120],
                    payload_preview=payload_preview,
                )
            )
    return responses


def _extract_response_body(text: str, responses: list[ParsedResponse]) -> str:
    inline = next((item.payload_preview for item in responses if item.payload_preview), "")
    if inline:
        return inline
    json_block = _extract_first_code_block(text, lang_hint="json")
    if json_block:
        return json_block[:2000]
    fields = _parse_markdown_field_table(text)
    if fields:
        return "markdown-schema:" + ",".join(field.name for field in fields)
    return ""


def to_summary(result: ValidationResult) -> dict[str, Any]:
    """Return a small dict useful for logging / WS event payloads."""
    return {
        "valid": result.valid,
        "code": result.code,
        "detail": result.detail,
        "missing_sections": result.missing_sections,
        "missing_fields": result.missing_fields,
        "field_errors": [item.model_dump() for item in result.field_errors],
        "warnings": result.warnings,
    }
