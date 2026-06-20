"""
tools/api_test_case_generator.py
────────────────────────────────
Rule-based API test case generator. Replaces the LLM-driven
``test_case_generator`` agent in the ``automation-testing-api`` pipeline
when a strong LLM is not available.

Strategy
========
Input is ``md_spec_parsed`` (already produced by ``md_api_spec_verifier``)
which carries ``endpoint``, ``request.body_fields``, and ``responses``.
This module emits a :class:`TestCaseOutput` containing:

1. **Happy-path** test cases — one per declared 2xx response.
2. **Required-field validation** — one per ``required=True`` body field
   (POST/PUT/PATCH only). The body omits exactly that one field and the
   case expects HTTP 400.
3. **Type-mismatch validation** — one per body field with a known type;
   the field is sent with a value of the wrong type and the case expects
   HTTP 400 (only emitted when the spec actually declares a 4xx response).
4. **Path-param 404** — when the path contains ``{id}`` / ``:id`` and the
   spec declares a 404 response, the case calls the endpoint with an ID
   guaranteed not to exist and expects 404.

The base URL is extracted from the raw markdown via a ``Base URL: …``
line. When absent, the cases are tagged ``executable=False`` and the
execution step will skip them.

This module never calls an LLM — output is deterministic.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from app.schemas.pipeline_io import (
    AutomationReadiness,
    CoverageSummary,
    TestCase,
    TestCaseOutput,
    TestCategory,
    TestLevel,
    TestStep,
    TestType,
)
from app.tools.md_api_spec_validator import ParsedField, ParsedSpec

logger = logging.getLogger(__name__)

# Methods that carry a request body — the only ones for which we emit
# field-validation cases.
_METHODS_WITH_BODY = {"POST", "PUT", "PATCH"}

# Plausible sample values per declared type. Picked to be both valid for
# the field AND distinct enough that swapping types triggers binding errors.
_SAMPLE_VALID: dict[str, Any] = {
    "string": "sample",
    "str": "sample",
    "text": "sample",
    "int": 1,
    "integer": 1,
    "uint": 1,
    "long": 1,
    "float": 1.5,
    "number": 1.5,
    "double": 1.5,
    "bool": True,
    "boolean": True,
    "date": "2026-01-25",
    "datetime": "2026-01-25T08:00:00Z",
    "time": "08:00",
    "object": {},
    "array": [],
    "json": {},
}

# Wrong-type values used to provoke 400 binding errors. Keyed by the
# declared field type — for ``string`` we send an int, for ``bool`` we
# send a string, etc.
_SAMPLE_WRONG_TYPE: dict[str, Any] = {
    "string": 12345,
    "str": 12345,
    "text": 12345,
    "int": "not-an-int",
    "integer": "not-an-int",
    "uint": "not-an-int",
    "long": "not-an-int",
    "float": "not-a-float",
    "number": "not-a-number",
    "double": "not-a-number",
    "bool": "not-a-bool",
    "boolean": "not-a-bool",
    "date": "not-a-date",
    "datetime": "not-a-datetime",
    "time": "not-a-time",
}

_RE_PATH_PARAM = re.compile(r"[:{](\w+)[}]?")


def generate_test_cases(
    parsed: ParsedSpec,
    document_content: str = "",
    requirement_ids: Optional[list[str]] = None,
) -> TestCaseOutput:
    """Build a deterministic :class:`TestCaseOutput` from a parsed MD spec.

    Args:
        parsed:            The :class:`ParsedSpec` emitted by
                           :func:`md_api_spec_validator.validate_md_api_spec`.
        document_content:  Retained for backward-compatible callers; normalized
                           URL/header data comes from ``parsed``.
        requirement_ids:   Optional traceability link. The first id is
                           attached to every generated test case so
                           coverage analysis downstream still works.

    Returns:
        :class:`TestCaseOutput` (model — call ``.model_dump()`` for storage).
    """
    endpoint = parsed.endpoint
    request = parsed.request
    responses = parsed.responses

    base_url = parsed.base_url
    full_url = (base_url.rstrip("/") + endpoint.path) if base_url else endpoint.path
    method = (endpoint.method or "GET").upper()
    requirement_id = (requirement_ids[0] if requirement_ids else "REQ-001")
    executable = bool(base_url)

    declared_statuses = {r.status_code for r in responses}
    has_4xx = any(400 <= s < 500 for s in declared_statuses)
    has_404 = 404 in declared_statuses
    has_path_param = bool(_RE_PATH_PARAM.search(endpoint.path or ""))

    cases: list[TestCase] = []
    counter = 1

    valid_body = _build_valid_body(request.body_fields)
    valid_headers: dict[str, str] = {}
    if request.content_type:
        valid_headers["Content-Type"] = request.content_type
    elif method in _METHODS_WITH_BODY:
        valid_headers["Content-Type"] = "application/json"
    for header in parsed.headers:
        if header.name.lower() == "content-type":
            continue
        env_name = re.sub(r"[^A-Z0-9]+", "_", header.name.upper()).strip("_")
        valid_headers.setdefault(header.name, f"${{HEADER_{env_name}}}")

    # ── 1. Happy-path per 2xx response ────────────────────────────────────
    for resp in responses:
        if not (200 <= resp.status_code < 300):
            continue
        cases.append(
            TestCase(
                id=f"TC-{counter:03d}",
                requirement_id=requirement_id,
                title=f"{method} {endpoint.path} — happy path expects {resp.status_code}",
                description=(
                    f"Send a valid {method} request to {endpoint.path}. "
                    f"Backend must return {resp.status_code}."
                ),
                preconditions=f"Target API reachable at {base_url or '<base-url>'}",
                steps=_build_happy_steps(method, full_url, resp.status_code),
                expected_result=(
                    f"HTTP {resp.status_code} with response body matching the "
                    "declared schema."
                ),
                test_type=TestType.API,
                category=TestCategory.POSITIVE,
                priority="high",
                tags=["happy-path", "rule-based"],
                api_endpoint=endpoint.path,
                http_method=method,
                request_headers=valid_headers or None,
                request_body=valid_body if method in _METHODS_WITH_BODY else None,
                expected_status_code=resp.status_code,
                test_level=TestLevel.INTEGRATION,
                executable=executable,
                classification_confidence=1.0,
                skip_reason=None if executable else "No Base URL declared in MD spec.",
            )
        )
        counter += 1

    # ── 2. Required-field validation (only if a 4xx is declared) ──────────
    if method in _METHODS_WITH_BODY and has_4xx:
        for field in request.body_fields:
            if not field.required:
                continue
            partial_body = {
                k: v for k, v in valid_body.items() if k != field.name
            }
            cases.append(
                TestCase(
                    id=f"TC-{counter:03d}",
                    requirement_id=requirement_id,
                    title=(
                        f"{method} {endpoint.path} — missing required "
                        f"`{field.name}` expects 400"
                    ),
                    description=(
                        f"Send a {method} request that omits the required "
                        f"`{field.name}` field. Backend must reject with 400."
                    ),
                    preconditions=f"Target API reachable at {base_url or '<base-url>'}",
                    steps=_build_validation_steps(
                        method, full_url, field.name, "omitted"
                    ),
                    expected_result=(
                        f"HTTP 400 with an error message referencing the "
                        f"missing field `{field.name}`."
                    ),
                    test_type=TestType.API,
                    category=TestCategory.NEGATIVE,
                    priority="medium",
                    tags=["validation", "required-field", "rule-based"],
                    api_endpoint=endpoint.path,
                    http_method=method,
                    request_headers=valid_headers or None,
                    request_body=partial_body,
                    expected_status_code=400,
                    test_level=TestLevel.INTEGRATION,
                    executable=executable,
                    classification_confidence=1.0,
                    skip_reason=None if executable else "No Base URL declared in MD spec.",
                )
            )
            counter += 1

    # ── 3. Type-mismatch validation ───────────────────────────────────────
    if method in _METHODS_WITH_BODY and has_4xx:
        for field in request.body_fields:
            wrong_value = _wrong_type_value(field.type)
            if wrong_value is None:
                continue
            mutated = dict(valid_body)
            mutated[field.name] = wrong_value
            cases.append(
                TestCase(
                    id=f"TC-{counter:03d}",
                    requirement_id=requirement_id,
                    title=(
                        f"{method} {endpoint.path} — wrong type for "
                        f"`{field.name}` expects 400"
                    ),
                    description=(
                        f"Send a {method} request where `{field.name}` is the "
                        f"wrong type (expected {field.type or 'any'}, sent "
                        f"{type(wrong_value).__name__}). Backend must reject "
                        "with 400."
                    ),
                    preconditions=f"Target API reachable at {base_url or '<base-url>'}",
                    steps=_build_validation_steps(
                        method, full_url, field.name, "wrong type"
                    ),
                    expected_result=(
                        "HTTP 400 with a JSON binding / validation error."
                    ),
                    test_type=TestType.API,
                    category=TestCategory.NEGATIVE,
                    priority="medium",
                    tags=["validation", "type-mismatch", "rule-based"],
                    api_endpoint=endpoint.path,
                    http_method=method,
                    request_headers=valid_headers or None,
                    request_body=mutated,
                    expected_status_code=400,
                    test_level=TestLevel.INTEGRATION,
                    executable=executable,
                    classification_confidence=1.0,
                    skip_reason=None if executable else "No Base URL declared in MD spec.",
                )
            )
            counter += 1

    # ── 4. Path-param 404 ─────────────────────────────────────────────────
    if has_path_param and has_404:
        unknown_url = _substitute_path_param(full_url, "999999999")
        unknown_path = _substitute_path_param(endpoint.path, "999999999")
        cases.append(
            TestCase(
                id=f"TC-{counter:03d}",
                requirement_id=requirement_id,
                title=(
                    f"{method} {endpoint.path} — unknown id expects 404"
                ),
                description=(
                    f"Send a {method} request using an id that does not exist "
                    "in the database. Backend must return 404."
                ),
                preconditions=f"Target API reachable at {base_url or '<base-url>'}",
                steps=_build_happy_steps(method, unknown_url, 404),
                expected_result="HTTP 404 with a `not found`-style error body.",
                test_type=TestType.API,
                category=TestCategory.NEGATIVE,
                priority="medium",
                tags=["not-found", "rule-based"],
                api_endpoint=unknown_path,
                http_method=method,
                request_headers=valid_headers or None,
                request_body=valid_body if method in _METHODS_WITH_BODY else None,
                expected_status_code=404,
                test_level=TestLevel.INTEGRATION,
                executable=executable,
                classification_confidence=1.0,
                skip_reason=None if executable else "No Base URL declared in MD spec.",
            )
        )
        counter += 1

    # ── Coverage & assembly ────────────────────────────────────────────────
    coverage = CoverageSummary(
        total_requirements=max(1, len(requirement_ids or [])),
        covered_requirements=1 if cases else 0,
        uncovered_requirements=[],
        by_type={"functional": 1},
        by_priority={"high": sum(1 for c in cases if c.priority == "high"),
                     "medium": sum(1 for c in cases if c.priority == "medium")},
        by_category={
            "positive": sum(1 for c in cases if c.category == TestCategory.POSITIVE),
            "negative": sum(1 for c in cases if c.category == TestCategory.NEGATIVE),
        },
        coverage_gaps=(
            [] if cases
            else [f"No test cases generated for {method} {endpoint.path}"]
        ),
    )

    notes: list[str] = [
        f"Rule-based generator: {len(cases)} test case(s) from "
        f"{method} {endpoint.path}.",
    ]
    if not executable:
        notes.append(
            "Base URL not found in MD spec — cases marked executable=False; "
            "execution step will skip them."
        )
    if not has_4xx:
        notes.append(
            "Spec declares no 4xx response — validation test cases were "
            "not emitted."
        )

    return TestCaseOutput(
        test_cases=cases,
        total_test_cases=len(cases),
        coverage_summary=coverage,
        automation_readiness=AutomationReadiness(
            total_automated=sum(1 for c in cases if c.executable),
            automation_percentage=(
                round(sum(1 for c in cases if c.executable) / len(cases) * 100, 1)
                if cases else 0.0
            ),
            frameworks_used=["httpx"] if cases else [],
        ),
        design_notes=notes,
        risks=(
            ["MD spec did not declare a Base URL — tests cannot run live."]
            if not executable else []
        ),
        recommendations=[
            "Verify rule-based cases reflect real behaviour and add LLM-driven "
            "edge cases once a stronger model is configured."
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _build_valid_body(fields: list[ParsedField]) -> dict[str, Any]:
    body: dict[str, Any] = {}
    for f in fields:
        body[f.name] = _sample_valid_value(f.type)
    return body


def _sample_valid_value(field_type: str) -> Any:
    key = (field_type or "").lower().strip()
    return _SAMPLE_VALID.get(key, "sample")


def _wrong_type_value(field_type: str) -> Any:
    key = (field_type or "").lower().strip()
    return _SAMPLE_WRONG_TYPE.get(key)


def _substitute_path_param(path: str, value: str) -> str:
    """Replace ``:id`` / ``{id}`` style path params with *value*."""
    out = re.sub(r"\{[^}]+\}", value, path)
    out = re.sub(r":\w+", value, out)
    return out


def _build_happy_steps(
    method: str,
    url: str,
    expected_status: int,
) -> list[TestStep]:
    return [
        TestStep(
            step_number=1,
            action=f"Send {method} {url}",
            expected_result=f"Receive HTTP {expected_status}",
        ),
        TestStep(
            step_number=2,
            action="Inspect response body",
            expected_result="Body matches the declared schema",
        ),
    ]


def _build_validation_steps(
    method: str,
    url: str,
    field_name: str,
    mutation: str,
) -> list[TestStep]:
    return [
        TestStep(
            step_number=1,
            action=(
                f"Build a request body where `{field_name}` is {mutation}"
            ),
            expected_result="Request payload prepared",
        ),
        TestStep(
            step_number=2,
            action=f"Send {method} {url}",
            expected_result="Receive HTTP 400",
        ),
        TestStep(
            step_number=3,
            action="Inspect error body",
            expected_result=(
                "Body contains an `error` field referencing the malformed input"
            ),
        ),
    ]
