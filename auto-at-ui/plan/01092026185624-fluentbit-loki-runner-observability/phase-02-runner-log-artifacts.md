# Phase 02 — Runner log and manifest staging artifacts

## Objective

Create bounded, redacted runner-event JSONL and integrity-manifest artifacts in the existing staging volume. Phase 03 promotes them to RustFS with every other evidence file.

## Paths and behavior

- Change `workers/playwright/src/execute.ts` to create a safe event sink and register `runner-log` (`application/x-ndjson`) and `artifact-manifest` (`application/json`) with existing `addEvidence`.
- Reuse `workers/playwright/src/observability.ts` from Phase 01; add worker execution tests; extend `tests/test_verified_artifacts.py` and optional `tests/test_playwright_worker_compose.py`.
- Record validation, browser start, step start/outcome, timeout/cancel, evidence collection, artifact creation, and terminal events only. Cap byte budget, append one truncation event at most, redact before event creation and serialization, and never alter verdict on log failure.
- Write `/artifacts/{run_id}/runner-log.jsonl`. Manifest includes schema version, run/correlation IDs, safe relative names, kind/type, checksum, size, and creation time, never absolute paths or bodies. Result remains v1 and returns contained `file://` staging URIs until Phase 03.

## Validation and non-goals

Run `npm.cmd run typecheck --prefix workers/playwright`, worker tests, and `uv run pytest tests/test_verified_artifacts.py`. Prove parseability, cap, redaction, checksum agreement, and no verdict change. Do not give the worker RustFS credentials, change visual-evidence policy, or copy raw Playwright output into JSONL.

## Completion record

- Status: completed 2026-09-01 19:20 +07:00.
- Delivered a 64 KiB capped event sink with one truncation event, recursive redaction, `runner-log` JSONL and checksum-backed `artifact-manifest` staging artifacts. Manifest entries exclude absolute paths and bodies; its own artifact checksum remains in v1 runner evidence metadata to avoid self-referential hashing.
- Validation: worker typecheck and tests passed (17 passed, 1 skipped); `uv run pytest tests/test_verified_artifacts.py --basetemp .pytest-phase2` passed (2 passed).
- Deviation: the default global pytest temporary directory is inaccessible on this Windows checkout, so a workspace-local temporary base was used for the existing artifact tests.
