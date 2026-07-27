# Test-generation agent implementation plan

This plan adds a governed path from a natural-language Web UI testing request to
a reviewed Playwright Test file and one deterministic execution. The existing
v1 runner contract and deterministic run path remain supported throughout.

## Progress board

| Progress | Phase | Product outcome |
| --- | --- | --- |
| Complete | [Phase 0 — boundaries and contracts](phase-00-boundaries-and-contracts.md) | Auditable interfaces and project execution policy within v1 |
| Complete | [Phase 1 — draft lifecycle and review API](phase-01-draft-lifecycle-and-review-api.md) | Persisted, authorized draft → approval → test case/run flow |
| Complete | [Phase 2 — governed planning agent](phase-02-governed-planning-agent.md) | Redacted, schema-validated Playwright Test drafts |
| Complete | [Phase 3 — isolated Playwright Test execution](phase-03-isolated-playwright-test-execution.md) | Approved test source runs safely with deterministic evidence |
| Complete | [Phase 4 — dashboard and end-to-end quality](phase-04-dashboard-and-end-to-end-quality.md) | Usable review UI and Compose-backed acceptance coverage |

**Overall progress:** 5/5 phases complete.

## Locked v1 decisions

- Both dashboard and REST API accept a target URL plus a natural-language test request.
- The planner returns a Playwright Test source draft with assumptions and stop conditions; it cannot access browser, shell, database, repository, or approval tools.
- Contributors, project administrators, and tenant administrators may submit and approve drafts for their authorized project. A service identity and a reviewer-only identity cannot approve a generated test for execution.
- A valid approval creates a versioned database test case and immediately creates/dispatches exactly one deterministic run. The system never writes a source repository or creates a review branch in this plan.
- Each project owns an HTTP(S) origin allowlist. Login and user-provided credentials are outside v1 scope.
- Generated test files are allowed to import only `@playwright/test`; arbitrary Node.js, shell, filesystem, process, package, and direct network APIs are prohibited. The worker executes validated source in an isolated temporary workspace.
- The v1 execution envelope remains unchanged. Approved generated source uses a validated `playwright_test_source` runner configuration within v1.

## Shared completion rule

Every phase preserves tenant isolation, RBAC, correlation IDs, append-only audit events, immutable decisions, and the runner as the sole verdict authority.
