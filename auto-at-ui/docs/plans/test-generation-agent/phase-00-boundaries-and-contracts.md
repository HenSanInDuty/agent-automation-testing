# Phase 0 — boundaries and contracts

**Status:** done  
**Exit:** The planning/review/execution data flow and authority boundary are
documented and covered by v1 contract fixtures.

## Checklist

- [x] Add an ADR for generated-test authority, source restrictions, origin
  allowlisting, no-login scope, and temporary-workspace execution.
- [x] Define versioned planning request/draft/decision schemas, including
  request hash, source hash, assumptions, stop conditions, provenance, state,
  and linked test case/run IDs.
- [x] Keep the v1 target-neutral execution request and define a validated,
  target-specific `playwright_test_source` runner configuration.
- [x] Define a project-scoped execution-policy schema containing allowed
  HTTP(S) origins and validate canonical origin matching.
- [x] Add Python/TypeScript v1 fixtures and compatibility tests.
- [x] Record data classification: redact natural-language input before model
  use/persistence; do not accept credentials; preserve only redacted content
  and reproducibility hashes in planning records.

## Completion demonstration

A valid existing v1 request and a valid v1 generated-test request both validate
in Python and TypeScript. Invalid source modes, non-HTTP(S) URLs, credentials,
and origins outside a project policy are rejected before dispatch.

## Validation

Focused contract/schema tests, redaction tests, Python/TypeScript fixture
compatibility tests, and `uv run ruff check .`.
