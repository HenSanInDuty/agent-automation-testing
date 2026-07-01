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
from app.tools.md_api_spec_validator import ParsedField, ParsedRequest, ParsedSpec
from app.tools.request_body_synthesizer import resolve_request_body

logger = logging.getLogger(__name__)

# Methods that carry a request body — the only ones for which we emit
# field-validation cases.
_METHODS_WITH_BODY = {"POST", "PUT", "PATCH"}

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

# Concrete id substituted into path params (`:id` / `{id}`) for happy-path and
# validation cases — a literal `:id` would never match a real route. The
# not-found case uses a deliberately non-existent id instead (see section 4).
_SAMPLE_PATH_ID = "1"


def generate_test_cases(
    parsed: ParsedSpec,
    document_content: str = "",
    requirement_ids: Optional[list[str]] = None,
    body_seeds: Optional[dict[str, dict[str, Any]]] = None,
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
        body_seeds:        Optional LLM-refined request bodies keyed by
                           ``"<METHOD> <path>"``. When a key matches an
                           endpoint, its values overlay the deterministic body
                           so happy-path / validation cases ship realistic
                           data. Absent / failed synthesis leaves the
                           deterministic body intact.

    Returns:
        :class:`TestCaseOutput` (model — call ``.model_dump()`` for storage).
    """
    base_url = parsed.base_url
    requirement_id = (requirement_ids[0] if requirement_ids else "REQ-001")
    executable = bool(base_url)

    cases: list[TestCase] = []
    counter = 1
    endpoint_paths: list[str] = []
    # Shared chaining context: collection base path → {create_tc, var}. Populated
    # by a POST create case and consumed by item (`/:id`) cases processed later.
    chain: dict[str, dict[str, str]] = {}
    seeds = body_seeds or {}
    for ep in parsed.endpoints:
        ep_cases, counter = _cases_for_endpoint(
            ep, base_url, parsed.headers, requirement_id, executable, counter,
            chain, seeds,
        )
        cases.extend(ep_cases)
        if ep.endpoint.path:
            endpoint_paths.append(ep.endpoint.path)

    return _assemble_output(
        cases=cases,
        endpoint_count=len(parsed.endpoints),
        endpoint_paths=endpoint_paths,
        requirement_ids=requirement_ids,
        executable=executable,
    )


def _cases_for_endpoint(
    ep: Any,
    base_url: str,
    spec_headers: list,
    requirement_id: str,
    executable: bool,
    counter: int,
    chain: dict[str, dict[str, str]],
    body_seeds: dict[str, dict[str, Any]],
) -> tuple[list[TestCase], int]:
    """Build the deterministic case matrix for ONE endpoint.

    The *counter* is threaded in and out so ``TC-NNN`` ids stay globally unique
    across every endpoint in the spec. *chain* carries cross-endpoint create →
    item linkage so a `/:id` case reuses the id captured from its POST create.
    *body_seeds* carries optional LLM-refined bodies keyed by ``"<METHOD> <path>"``.
    """
    endpoint = ep.endpoint
    request = ep.request
    responses = ep.responses

    method = (endpoint.method or "GET").upper()
    seed = body_seeds.get(f"{method} {endpoint.path}")

    declared_statuses = {r.status_code for r in responses}
    has_4xx = any(400 <= s < 500 for s in declared_statuses)
    has_404 = 404 in declared_statuses
    has_path_param = bool(_RE_PATH_PARAM.search(endpoint.path or ""))

    # Chaining: an item endpoint (`/api/tasks/:id`) reuses the id captured from
    # the create (POST) of its collection when one exists; otherwise it falls
    # back to a sample id. The 404 case never chains (it needs a missing id).
    collection_base = _collection_base(endpoint.path)
    is_create = method == "POST" and not has_path_param
    link = chain.get(collection_base) if has_path_param else None
    if link:
        id_token = "{" + link["var"] + "}"
        chain_depends = [link["create_tc"]]
        path_note = (
            f" Path id `{{{link['var']}}}` is captured from the create response "
            f"of {link['create_tc']}."
        )
    elif has_path_param:
        id_token = _SAMPLE_PATH_ID
        chain_depends = []
        path_note = (
            f" Path param resolved to sample id `{_SAMPLE_PATH_ID}`; "
            "requires that resource to exist."
        )
    else:
        id_token = _SAMPLE_PATH_ID
        chain_depends = []
        path_note = ""

    # Substitute on the PATH only, then join the base URL — substituting on a
    # full URL would corrupt the `:port` (e.g. `:8080` → the id token).
    resolved_path = (
        _substitute_path_param(endpoint.path, id_token)
        if has_path_param else endpoint.path
    )
    resolved_url = (base_url.rstrip("/") + resolved_path) if base_url else resolved_path

    cases: list[TestCase] = []

    valid_body = _build_valid_body(request, seed)
    valid_headers: dict[str, str] = {}
    if request.content_type:
        valid_headers["Content-Type"] = request.content_type
    elif method in _METHODS_WITH_BODY:
        valid_headers["Content-Type"] = "application/json"
    for header in spec_headers:
        if header.name.lower() == "content-type":
            continue
        env_name = re.sub(r"[^A-Z0-9]+", "_", header.name.upper()).strip("_")
        valid_headers.setdefault(header.name, f"${{HEADER_{env_name}}}")

    # ── 1. Happy-path per 2xx response ────────────────────────────────────
    for resp in responses:
        if not (200 <= resp.status_code < 300):
            continue
        case_id = f"TC-{counter:03d}"
        # A POST create exposes its `id` so later item cases can chain off it.
        extract: dict[str, str] = {}
        if is_create and collection_base not in chain:
            var = _var_for(collection_base)
            extract = {var: "id"}
            chain[collection_base] = {"create_tc": case_id, "var": var}
        cases.append(
            TestCase(
                id=case_id,
                requirement_id=requirement_id,
                title=f"{method} {endpoint.path} — happy path expects {resp.status_code}",
                description=(
                    f"Send a valid {method} request to {endpoint.path}. "
                    f"Backend must return {resp.status_code}."
                ),
                preconditions=f"Target API reachable at {base_url or '<base-url>'}.{path_note}",
                steps=_build_happy_steps(method, resolved_url, resp.status_code),
                expected_result=(
                    f"HTTP {resp.status_code} with response body matching the "
                    "declared schema."
                ),
                test_type=TestType.API,
                category=TestCategory.POSITIVE,
                priority="high",
                tags=["happy-path", "rule-based"],
                api_endpoint=resolved_path,
                http_method=method,
                request_headers=valid_headers or None,
                request_body=valid_body if method in _METHODS_WITH_BODY else None,
                expected_status_code=resp.status_code,
                test_level=TestLevel.INTEGRATION,
                executable=executable,
                classification_confidence=1.0,
                skip_reason=None if executable else "No Base URL declared in MD spec.",
                depends_on=list(chain_depends),
                extract=extract,
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
                    preconditions=f"Target API reachable at {base_url or '<base-url>'}.{path_note}",
                    steps=_build_validation_steps(
                        method, resolved_url, field.name, "omitted"
                    ),
                    expected_result=(
                        f"HTTP 400 with an error message referencing the "
                        f"missing field `{field.name}`."
                    ),
                    test_type=TestType.API,
                    category=TestCategory.NEGATIVE,
                    priority="medium",
                    tags=["validation", "required-field", "rule-based"],
                    api_endpoint=resolved_path,
                    http_method=method,
                    request_headers=valid_headers or None,
                    request_body=partial_body,
                    expected_status_code=400,
                    test_level=TestLevel.INTEGRATION,
                    executable=executable,
                    classification_confidence=1.0,
                    skip_reason=None if executable else "No Base URL declared in MD spec.",
                    depends_on=list(chain_depends),
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
                    preconditions=f"Target API reachable at {base_url or '<base-url>'}.{path_note}",
                    steps=_build_validation_steps(
                        method, resolved_url, field.name, "wrong type"
                    ),
                    expected_result=(
                        "HTTP 400 with a JSON binding / validation error."
                    ),
                    test_type=TestType.API,
                    category=TestCategory.NEGATIVE,
                    priority="medium",
                    tags=["validation", "type-mismatch", "rule-based"],
                    api_endpoint=resolved_path,
                    http_method=method,
                    request_headers=valid_headers or None,
                    request_body=mutated,
                    expected_status_code=400,
                    test_level=TestLevel.INTEGRATION,
                    executable=executable,
                    classification_confidence=1.0,
                    skip_reason=None if executable else "No Base URL declared in MD spec.",
                    depends_on=list(chain_depends),
                )
            )
            counter += 1

    # ── 4. Path-param 404 ─────────────────────────────────────────────────
    if has_path_param and has_404:
        unknown_path = _substitute_path_param(endpoint.path, "999999999")
        unknown_url = (
            (base_url.rstrip("/") + unknown_path) if base_url else unknown_path
        )
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

    return cases, counter


def _assemble_output(
    *,
    cases: list[TestCase],
    endpoint_count: int,
    endpoint_paths: list[str],
    requirement_ids: Optional[list[str]],
    executable: bool,
) -> TestCaseOutput:
    """Wrap the accumulated multi-endpoint cases into a :class:`TestCaseOutput`.

    The authoritative obligation-coverage gate lives in
    ``services/api_test_planning/coverage.py``; this requirement-level
    ``CoverageSummary`` is a human-facing rollup only.
    """
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
            [] if cases else ["No test cases generated from the parsed spec."]
        ),
    )

    notes: list[str] = [
        f"Rule-based generator: {len(cases)} test case(s) from "
        f"{endpoint_count} endpoint(s) — "
        f"{', '.join(dict.fromkeys(endpoint_paths)) or 'no paths'}.",
    ]
    if not executable:
        notes.append(
            "Base URL not found in MD spec — cases marked executable=False; "
            "execution step will skip them."
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


def _build_valid_body(
    request: ParsedRequest,
    seed: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build a representative request body for happy-path / validation cases.

    The deterministic :func:`request_body_synthesizer.resolve_request_body`
    handles both spec formats (contract §3.2): a JSON example block has its
    schema-placeholder tokens (``"YYYY-MM-DD"``, ``"HH:mm"``, ``"string"`` …)
    replaced with valid values while real example values pass through; a
    markdown field table is sampled per declared type.

    When *seed* is supplied (an LLM-refined body), its values overlay the
    deterministic body so each present field ships realistic data. Missing keys
    always retain the deterministic value, so the body is never left incomplete.
    """
    body = resolve_request_body(request)
    if isinstance(seed, dict):
        for key, value in seed.items():
            if value is not None:
                body[key] = value
    return body


def _wrong_type_value(field_type: str) -> Any:
    key = (field_type or "").lower().strip()
    return _SAMPLE_WRONG_TYPE.get(key)


def _collection_base(path: str) -> str:
    """Strip a trailing path-param segment: ``/api/tasks/:id`` → ``/api/tasks``.

    Used to match an item endpoint back to its collection's create (POST) so a
    captured id can be reused.
    """
    return re.sub(r"/[:{][^/]+$", "", path or "")


def _var_for(base: str) -> str:
    """Chain variable name for a collection base, e.g. ``/api/tasks`` → ``tasks_id``."""
    segment = (base or "").rstrip("/").split("/")[-1] or "resource"
    segment = re.sub(r"[^A-Za-z0-9]+", "_", segment).strip("_") or "resource"
    return f"{segment}_id"


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
