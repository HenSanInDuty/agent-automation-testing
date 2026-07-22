# Phase 2 — Web UI vertical slice

**Status:** done
**Prerequisite:** Phase 1 complete  
**Exit:** Docker Compose runs a version-pinned Playwright test and exposes its
deterministic result plus verified evidence through the control plane.

## Checklist

- [x] Define Python/TypeScript contract fixtures and schema tests for execution
  contract v1.
- [x] Implement runner dispatch and a local transport port replaceable by a
  workflow transport later.
- [x] Implement Playwright worker request validation, version-pinned execution,
  per-step timeout, and target-specific config handling.
- [x] Collect URL, step history, accessibility snapshot, bounded DOM fragment,
  screenshots, trace, console errors, and network failures where applicable.
- [x] Upload binary evidence via the artifact port; persist URI, checksum, size,
  and content type; verify checksum before trusting the URI.
- [x] Persist only the worker's result as terminal status; expose run/artifact
  queries through the API.
- [x] Add worker unit/contract tests and Compose-backed pass/failure tests.

## Completion demonstration

One API request runs a seeded browser test. Pass and functional failure are both
reported exactly as determined by Playwright; failure evidence is retrievable
without an LLM.

**Exit validation (2026-07-22):** Docker Compose applies Alembic migrations
before starting the control plane. Seeded pass and functional-failure requests
through the run API returned the Playwright verdict, listed verified failure
artifacts, and downloaded a trace successfully.

## Validation

Python checks, TypeScript lint/type check, Playwright contract tests, and Compose
integration tests.
