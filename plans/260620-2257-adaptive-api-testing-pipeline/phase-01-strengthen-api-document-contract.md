---
phase: 1
title: "Strengthen API document contract"
status: pending
priority: P1
dependencies: []
---

# Phase 1: Strengthen API document contract

## Overview

Make document validation deterministic and fail-fast before run creation, ingestion, or LLM calls. Extend the current contract instead of adding another parser.

## Requirements

- Require non-empty base URL, endpoint path, HTTP method, request body, response body, and headers.
- Return one structured error containing every missing/invalid item; do not stop at the first omission.
- Preserve `strict=false` compatibility by converting violations to warnings.
- Treat body-less methods explicitly: current requirement says request body is always required; document this policy rather than silently exempting GET/DELETE.
- For the API template, return HTTP 422 before scheduling background work; keep the DAG guard for derived/legacy entry paths.

## Architecture

Extend `ParsedSpec` with `base_url` and declared headers. Refactor validation into collect-all checks. Reuse it in request-time preflight for `automation-testing-api`, then raise the same structured contract through `MDSpecVerifierCrew` if a non-preflight path reaches the DAG. The `at-api-md-verifier` node stays retry-free.

## Related Code Files

- Modify: `D:/CV/auto-at/backend/app/tools/md_api_spec_validator.py` - parse and validate all six required elements.
- Modify: `D:/CV/auto-at/backend/app/crews/md_spec_verifier_crew.py` - forward normalized contract and combined failures.
- Modify: `D:/CV/auto-at/backend/app/core/errors.py` - keep stable machine-readable field codes.
- Modify: `D:/CV/auto-at/backend/app/api/v1/pipeline/runs.py` and `_helpers.py` - template-scoped preflight, 422 mapping, upload cleanup.
- Modify: `D:/CV/auto-at/backend/app/tools/api_test_case_generator.py` - consume parsed base URL/headers; remove raw-text recovery.
- Modify: `D:/CV/auto-at/backend/tests/test_md_api_spec_validator.py` and fixtures - compatibility and missing-field matrix.
- Modify: `D:/CV/auto-at/backend/tests/test_phase15.py` and run-route tests - fail-fast/preflight assertions.

## Implementation Steps

1. Define canonical field names and error codes: `base_url`, `endpoint.path`, `endpoint.method`, `request.body`, `response.body`, `headers`.
2. Parse base URL and headers into typed models; reject malformed URL, unsupported method, invalid path, empty schemas, and duplicate conflicting headers.
3. Accumulate all violations into `missing_sections`, `missing_fields`, and field-level details before returning/raising.
4. Treat document headers as names/schema/examples. Resolve real secret credentials at runtime and never require them in the document.
5. Run preflight after safe extraction but before DB run creation/background scheduling; remove temporary upload on 422 and return the same structured fields.
6. Forward normalized spec and warnings downstream; retain the DAG validator as defense in depth.
7. Add table-driven tests for each missing field, all-missing input, invalid values, synonyms, non-strict mode, immediate 422/no orphan state, and a valid document.

## Success Criteria

- [ ] All six required elements are typed and available downstream.
- [ ] Invalid upload returns 422 with all omissions; no run, background task, or orphan upload remains.
- [ ] No secret header value appears in errors, events, logs, or test snapshots.
- [ ] Existing valid fixtures are migrated or explicitly covered by compatibility policy.
- [ ] Validator and run-route test suites pass.

## Risk Assessment

HIGH validator blast radius: nine direct consumers/tests. Route impact is LOW but spans five flows. Mitigate with contract fixtures, stable error shape, non-strict compatibility, template-scoped preflight, and cleanup tests. Literal body/header requirements may reject conventional GET specs; confirm policy before implementation.
