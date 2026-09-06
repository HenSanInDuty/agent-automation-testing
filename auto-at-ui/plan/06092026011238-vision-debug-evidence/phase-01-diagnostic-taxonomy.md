# Phase 01 — Diagnostic taxonomy

## Objective

Replace the broad Vision candidate-batch failure collapse with a stable, safe,
non-payload diagnostic result that later phases can encrypt and expose only to an
administrator.

## Scope and prerequisites

- No database, HTTP, UI, or provider changes in this phase.
- Read `apps/control-plane/agents/vision/executor.py` and `service.py`; retain their
  strict action schema and fail-closed behavior.

## Changes

1. Add a Vision-internal typed diagnostic result/error in
   `apps/control-plane/agents/vision/` with an allow-listed code set, for example:
   `provider_transport`, `provider_http`, `response_not_object`,
   `response_missing_choices`, `response_missing_content`, `invalid_json`,
   `invalid_root_shape`, `invalid_candidate_schema`, `empty_candidates`,
   `candidate_limit_exceeded`, `redaction_failed`, and `payload_too_large`.
2. Refactor `_content_from_response`, `_json_value`, and
   `validate_visual_candidate_batch_output` to raise the typed failure while retaining
   Python exception chaining only internally. Do not serialize exception text.
3. Refactor `execute_visual_candidate_batch` so model invocation errors and validation
   errors are separately mapped. Extend `VisualCandidateBatchOutcome` with safe,
   non-secret diagnostic fields needed by later phases: code, provider status/category
   when available, and redacted capture candidate input. Keep the existing public
   `detail` generic.
4. Define a bounded raw-capture handoff type that accepts only text model content plus
   allow-listed provider envelope facts. It must reject screenshots, image URLs,
   prompt/messages, headers, request body, exception repr/traceback, and arbitrary
   response dictionaries.
5. Ensure all error paths remain unavailable/fail-closed; no fallback candidate, retry,
   traversal change, or verdict mutation is introduced.

## Tests and validation

- Extend `tests/test_vision_executor.py` for every code, Markdown-fenced valid JSON,
  malformed JSON, invalid root, missing response fields, wrong action schema, empty or
  oversized candidate list, provider transport error, and generic public detail.
- Add redaction/size-bound handoff unit tests using synthetic secrets and hostile text.
- Run `uv run pytest tests/test_vision_executor.py tests/test_vision_contracts.py` and
  `uv run ruff check apps/control-plane/agents/vision tests/test_vision_executor.py`.

## Acceptance criteria

- A test can distinguish each allow-listed failure code without receiving raw output.
- Existing valid candidate batches still produce identical validated `VisualAction`s.
- No standard response, activity event, or log gains raw model content.

## Risks and non-goals

Do not expose Python class names, provider diagnostic strings, or stack traces as codes.
This phase defines classification only; it stores nothing and grants no new access.

## Completion record

- Status: completed 2026-09-06T03:09:25+07:00.
- Implemented `VisualDiagnosticCode` / `VisualDiagnosticFailure`, strict batch
  classification, provider transport/HTTP classification, and a text-only bounded
  redacted `VisualDiagnosticCapture` with SHA-256 checksum.
- Changed: `apps/control-plane/agents/vision/diagnostics.py`, `executor.py`,
  `service.py`, and `tests/test_vision_executor.py`.
- Validated: `uv run pytest tests/test_vision_executor.py tests/test_vision_contracts.py`
  (17 passed); `uv run ruff check apps/control-plane/agents/vision
  tests/test_vision_executor.py` (passed); `git diff --check` (passed).
- Deviation: none. No raw payload has been stored or added to ordinary responses.
