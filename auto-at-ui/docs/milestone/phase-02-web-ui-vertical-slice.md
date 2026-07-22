# Phase 2 — Web UI vertical slice

**Status:** in progress
**Prerequisite:** Phase 1 complete  
**Exit:** Docker Compose runs a version-pinned Playwright test and exposes its
deterministic result plus verified evidence through the control plane.

## Checklist

- [x] Define Python/TypeScript contract fixtures and schema tests for execution
  contract v1.
- [x] Implement runner dispatch and a local transport port replaceable by a
  workflow transport later.
- [ ] Implement Playwright worker request validation, version-pinned execution,
  per-step timeout, and target-specific config handling.
- [ ] Collect URL, step history, accessibility snapshot, bounded DOM fragment,
  screenshots, trace, console errors, and network failures where applicable.
- [x] Upload binary evidence via the artifact port; persist URI, checksum, size,
  and content type; verify checksum before trusting the URI.
- [x] Persist only the worker's result as terminal status; expose run/artifact
  queries through the API.
- [ ] Add worker unit/contract tests and Compose-backed pass/failure tests.

## Completion demonstration

One API request runs a seeded browser test. Pass and functional failure are both
reported exactly as determined by Playwright; failure evidence is retrievable
without an LLM.

## Validation

Python checks, TypeScript lint/type check, Playwright contract tests, and Compose
integration tests.
