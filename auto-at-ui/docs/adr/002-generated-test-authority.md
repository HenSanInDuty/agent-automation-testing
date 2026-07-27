# ADR-002: Governed generated-test authority

- Status: Accepted
- Date: 2026-07-27

## Context

The platform will turn a natural-language Web UI testing request into a
Playwright Test draft.  Generated source is untrusted input: it must not gain
authority to change a repository, approve itself, or determine a test verdict.

## Decision

- The planner is advisory only. It has no browser, shell, database,
  repository, dispatch, or approval tools.
- A generated draft contains only redacted request text, reproducibility
  hashes, provenance, assumptions, and stop conditions. Raw requests and
  credentials are not persisted or sent to a model. Login and supplied
  credentials are outside v1 scope.
- A project execution policy owns an allowlist of canonical HTTP(S) origins.
  The control plane rejects credentials, non-HTTP(S) URLs, and origins outside
  that policy before dispatch.
- Generated TypeScript may import only `@playwright/test`; Node.js, shell,
  filesystem, process, package, and direct network APIs are prohibited.
- Approval is immutable and human-authorized. The approval flow, not the
  planner, creates a test case and exactly one deterministic run. The runner
  remains the sole authority for a verdict.
- Generated source is executed only from an isolated temporary workspace. It
  is never written to a source repository or review branch by this feature.

## Consequences

The existing v1 execution request remains the only cross-language request.
The target-specific `playwright_test_source` runner configuration is validated
before browser startup without changing the v1 envelope.
