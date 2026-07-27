# Phase 3 — isolated Playwright Test execution

**Status:** complete  
**Prerequisite:** Phases 0–2 complete  
**Exit:** The worker runs only an approved, hash-verified Playwright Test in an
isolated workspace, enforces project origins, and returns the normal v1
deterministic result/evidence contract.

## Checklist

- [x] Add a v1 `playwright_test_source` execution path. Verify the stored
  source hash before writing one temporary test file, run the pinned Playwright
  Test runner, and always remove the workspace.
- [x] Parse source with a TypeScript AST before execution. Permit imports only
  from `@playwright/test` and reject Node.js, shell, filesystem, process,
  package-loader, and direct-network APIs; record a safe policy failure.
- [x] Execute as a non-root user with read-only application inputs, no source
  repository or Docker socket mounts, bounded CPU/memory/time, and writable
  temporary/artifact directories only.
- [x] Apply the project HTTP(S) origin allowlist to initial navigation,
  redirects, popups, frames, and browser requests. Block all other origins and
  record the attempted destination as redacted evidence.
- [x] Normalize pass, failure, timeout, cancellation, and policy-blocked output
  into `TestExecutionResult` v1 with trace, screenshot, video, console,
  network, source-hash, and policy evidence.
- [x] Keep the existing v1 step-DSL execution and cancellation behavior
  unchanged; the runner remains the only verdict authority.

## Completion demonstration

An approved source test passes and a functional failure is reported by
Playwright. A prohibited import, hash mismatch, or redirect outside the
allowlist never executes successfully and leaves audit/evidence explaining the
block.

## Validation

TypeScript AST/source-policy tests, v1 contract and step-DSL regression tests,
and Compose-backed pass/failure/hash-mismatch/blocked-origin scenarios.

## Completed implementation

The worker writes only the approved, hash-verified source into a temporary
workspace, invokes the pinned Playwright Test runner, captures runner output
and Playwright artifacts, and removes the workspace in all outcomes. An AST
policy check blocks dangerous APIs before runner startup. The project policy is
snapshotted into the dispatched runner configuration and an injected worker
guard aborts browser destinations outside that allowlist while recording only
redacted origin evidence. The Compose worker runs as `pwuser` with a read-only
root filesystem, a bounded temporary filesystem, dropped capabilities, and
CPU/memory/PID limits.
