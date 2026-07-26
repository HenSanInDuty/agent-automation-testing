# ADR-003: Provider-neutral governed agent runtime through OpenRouter

- Status: Accepted
- Date: 2026-07-26

## Decision

Use OpenRouter as the initial model gateway, but keep the application boundary
provider-neutral. The selected provider/model, optional fallback, evidence
classes, and per-step guards are non-secret tenant-scoped configuration values.
They are stored in `configs` for a later admin UI and bootstrap from environment
defaults. API credentials are never persisted in that table: they stay in the
environment or a future secret manager.

## Guardrails

- Evidence modes are independently enabled for metadata, redacted text, and
  screenshots. Raw binary artifacts and unredacted sensitive inputs remain
  in artifact storage and never enter a prompt.
- Each agent step has a token ceiling and evidence-byte ceiling; each run has a
  maximum number of agent steps. These are research guards rather than a fixed
  currency budget.
- Concurrency defaults to one. Rate limiting is deliberately disabled for the
  local research stage.
- Fallback is configurable: either a named secondary provider/model or no
  fallback, which records triage as unavailable. It never changes a run verdict.
- Every proposal records provider/model, prompt, policy and input-hash versions
  when the proposal persistence work is added.

## Consequences

Changing models does not change agent-domain code. An admin UI can later edit
validated, non-secret config records. A model credential rotation does not
require a database mutation.
