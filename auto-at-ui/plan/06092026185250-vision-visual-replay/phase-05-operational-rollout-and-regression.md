# Phase 05 — Operational rollout and regression

## Objective

Finish the permanent replay-evidence feature with documented data handling,
migration/deletion operations, observability, and regression validation.

## Scope and prerequisites

- Requires all preceding phases.
- Does not enable Vision for a tenant, call a paid provider, choose production
  infrastructure, or process production data.

## Exact paths

- Change `docs/vision-agent-operations.md`, `docs/operations.md`,
  `docs/api-examples.md`, and ADR-006 from Phase 01 if review requests a final
  wording update.
- Change deployment/migration documentation only where it currently describes
  RustFS artifacts or Vision data handling.
- Add integration coverage in the existing Vision/RustFS/route test modules;
  use a synthetic PNG fixture only.

## Detailed behavior and data flow

1. Document the exact classification: private replay frame, indefinite
   persistence until tenant-admin deletion, no automatic cleanup, no public
   URL, viewer read scope, audit records, and known production approval gate.
2. Document forward migration order: apply database migration before processor
   deployment, confirm RustFS bucket/key policy permits the new private prefix,
   run a synthetic capture/read/delete smoke test, and do not backfill old
   sessions.
3. Document operational response to partial deletion: preserve metadata for
   retry, inspect only safe audit/aggregate counts, and never copy screenshots,
   object keys, URLs, prompts, or provider output into logs/tickets/Grafana.
4. Add aggregate observability for capture success/failure, verified-byte
   reads, deletion requested/completed/failed, orphan reconciliation counts,
   and retained count/bytes. Exclude tenant/session/correlation IDs and all
   image/prompt content from labels and messages.
5. Run an end-to-end synthetic fixture through capture, list, authenticated
   frame read, overlay metadata, explicit deletion, and denied cross-tenant
   access. Confirm no action affects an approved draft or test verdict.

## Contract/API/schema changes

No new changes should be introduced here. Any discovered contract change returns
to its owning phase for review rather than being patched into rollout.

## Tests and validation

Run the smallest focused suites during each phase, then the baseline:

```powershell
uv run ruff check .
uv run pytest
```

Run the dashboard's existing test, typecheck, lint, and build commands and the
worker contract tests. Also run `git diff --check` and apply the Alembic
migration against a disposable local PostgreSQL database.

## Acceptance criteria

Operators can deploy, verify, audit, and explicitly delete replay evidence
without exposing sensitive screenshots or changing Vision/execution behavior;
the full regression suite passes.

## Risks and non-goals

This phase does not grant authority to enable a tenant, choose a production
data region or storage vendor, or declare production privacy/legal approval.

## Execution record

Status: completed 2026-09-06 19:52 ICT.

The final operational records document private replay classification, permanent
until-authorized-deletion retention, forward migration/deployment order,
synthetic capture/read/delete validation, no historical backfill, safe
byte-before-metadata retry handling, aggregate-only observability, and the
production privacy/legal gate. Existing synthetic lifecycle tests cover capture,
authorized access, deletion, and cross-tenant denial without changing an
advisory draft or deterministic test verdict.

Validation: `uv run ruff check .` and `uv run pytest -q` (229 passed);
dashboard tests (20 passed), typecheck, lint, and build; worker typecheck and
explicit contract test (14 passed, 1 browser-image test skipped); disposable
PostgreSQL migration through `f7a8b9c0d1e2`; and `git diff --check` all passed.
The default worker test-discovery command remains unconfigured for the source
spec and therefore found no tests; running the explicit existing contract spec
provided the required worker validation. Non-failing Next.js/Node/color
warnings were recorded. No deviations or deferred work remain within this plan.
