# Phase 01 — Contracts, provider policy and durable metadata

Status: **completed**. Started: 2026-10-23 20:38 +07:00. Completed: 2026-10-23 20:51 +07:00. Dependencies: none. Read the canonical [README](README.md) first.

## Implementation evidence

Added the five planned contract/domain/migration/test paths and ADR below. Changed
all listed source files. `tests/test_vision_migration_compatibility.py` was run
unchanged; its imported helper in `tests/test_vision_handoff_repository.py` was
updated for the new migration head and null legacy consent assertion.

Additional compatibility paths: `apps/control-plane/application/vision_policy.py`
fails Codex readiness closed; `apps/control-plane/api/v1/routes/vision.py` accepts
the additive catalogue/policy response shape;
`tests/test_vision_policy_routes.py` checks the additive disabled catalogue item.
No changes to execution v1, dependency manifests, tenant data or prompts.

Validation:
- `uv run ruff check .`: passed.
- `uv run pytest tests/test_codex_bridge_contracts.py tests/test_vision_policy.py tests/test_agent_runtime.py tests/test_config.py tests/test_vision_policy_routes.py tests/test_codex_bridge_migrations.py tests/test_vision_migration_compatibility.py -q`: 139 passed, 6 existing fixture/deprecation warnings.
- After provider-switch consent refinement: `uv run pytest tests/test_agent_runtime.py tests/test_codex_bridge_contracts.py -q`: 78 passed.
- New migration upgrades the prior head with legacy rows and checks scoped FK,
  uniqueness, immutable consent/identity and terminal updates against owned PostgreSQL.
- Initial lint issues fixed; initial migration assertion expected the wrong
  exception wrapper, corrected to ProgrammingError and rerun successfully.
- Broader initial run failed due to shared temp-directory ACLs, an Alembic logging
  state leak and a generator change during that running process. Restored logger
  state and used a new owned `--basetemp`; stable full run passed 731 tests (exact
  command in README). Final UTF-8 output-byte guard then passed 53 contract tests
  and Ruff; a second full run after that isolated guard was not needed/run.

Deviation: minimal API/catalogue compatibility edits were pulled forward to avoid
breaking current readers or falsely claiming readiness from an HF key. The
database additionally enforces immutable snapshots and terminal transitions via
triggers; phase 05 repositories must also apply the pure guards under locks.
Readiness, CLI access/sandbox, raw DOM redaction and real-model quality remain
unqualified until their later phases. No CLI invocation occurred.

## Objective and scope

Define the opt-in Codex provider, separate DOM/image consent, immutable per-session input policy and scoped bridge job contracts. Make later worker/bridge phases testable without invoking Codex.

## Exact paths

Add:
- `packages/contracts/src/auto_at/contracts/codex_bridge.py`: versioned observation, request, response, receipt and usage models.
- `apps/control-plane/domain/codex_bridge.py`: pure lifecycle/scope/hash/deadline rules.
- `migrations/versions/c0d1e2f3a4b5_add_codex_bridge_metadata.py`: additive session snapshot, nullable proposal target binding and scoped model job table; confirm revision ID unused and set actual current head as parent.
- `tests/test_codex_bridge_contracts.py`, `tests/test_codex_bridge_migrations.py`.
- `docs/adr/010-codex-local-dom-agent.md`: confirmed local-only decision and operating boundaries.

Change:
- `apps/control-plane/agents/shared/vision_providers.py`, `apps/control-plane/agents/shared/runtime.py`, `apps/control-plane/config.py`.
- `apps/control-plane/domain/ports.py`, `apps/control-plane/domain/entities.py`, `apps/control-plane/domain/vision.py`.
- `apps/control-plane/infrastructure/persistence/models.py`.
- `tests/test_vision_policy.py`, `tests/test_agent_runtime.py`, `tests/test_config.py`, `tests/test_vision_migration_compatibility.py`.

## Behavior and contract design

1. Add `codex_cli` with exactly `gpt-6-luna` to the provider catalogue. Retain current HF/Gemini defaults and validations. No global provider switch.
2. Add optional `codex` policy object: `input_mode=dom_first`, `dom_transfer_accepted`, provider-bound `dom_transfer_provider`, `max_dom_elements=100`, `max_dom_bytes=65536`. Enabled Codex requires explicit DOM consent. Image permission remains independent in existing provider-bound screenshot fields. HF/Gemini still require their existing image permission. Switching recipient clears both forms of consent and enablement.
3. Settings owns host/container spool paths, bridge ID, allowed tenant, executable path, enable flag and local lifecycle limits. Settings must reject relative roots and invalid executable configuration; jobs cannot override these. Existing login is the only supported Codex auth mode. Do not add API-key settings for this feature.
4. `CodexDomObservation` v1: identity, observation/snapshot UUID, public state fingerprint, capture timestamp, bounded viewport, elements, truncation/unsupported indicators. Model-visible element: opaque ID, safe role/name/type, enabled/editable flags. Worker binding: validated descriptor plus normalized bounds; not a model-supplied selector. Distinguish the model-visible and trusted-binding projections.
5. `CodexBridgeRequest` v1 binds job/bridge/tenant/project/session, session fencing token, request sequence, snapshot ID/fingerprint, provider/model, prompt version, stage (`dom` or `image`), deadline, consent snapshot/hash, input hashes, candidate limit and per-job byte limits. Envelope field/filename sets are closed. No arbitrary filesystem paths, commands, model names, URLs or environment variables.
6. Model output has a closed union: `candidates`, `need_screenshot` or `stop`. DOM click/type candidates require an element ID; image candidates may use existing normalized coordinates. Define bounded confidence/outcome, text and scroll/wait limits consistent with existing VisualAction. No scripts, navigation URLs, arbitrary selectors or verdicts.
7. Trusted bridge response wraps output with exact request identity/hash, actual model if reported, CLI version, stage, timing, safe failure code, optional usage. The model does not generate trusted identity/provenance.
8. Add nullable immutable `model_input_policy` JSONB on sessions. Existing null means legacy behavior, never inferred Codex consent.
9. Add nullable `target_binding` JSONB to `VisualActionProposalModel`, with a typed `CodexProposalBinding` contract: observation/snapshot ID, opaque element ID, state fingerprint and sanitized expected descriptor. Keep it separate from existing action JSON so old action parsers remain valid. Existing proposals default to null. This is safe target metadata, not a raw DOM archive or authority to skip fresh grounding.
10. Add `codex_bridge_jobs` metadata: scoped IDs/correlation, request sequence, stage, request hash/snapshot/fence, queued/claimed/running/completed/failed/cancelled/expired status, deadline/timestamps, response hash, safe reason, optional usage and CLI/model provenance. Composite session scope FK, unique (session, request_sequence), immutable identity, and guarded terminal transitions. No raw DOM/image/prompt/output payload or auth in DB.
11. Declare job repository and readiness/spool ports in domain. Persistence implementations arrive in phase 5. Stable failure codes include bridge offline, unsupported CLI, login required, model unavailable, stale result, malformed output, cancelled and deadline exceeded; map provider-compatible ones to existing safe reasons where appropriate.

## Validation and acceptance

Run with `uv`:
- `uv run ruff check .`
- `uv run pytest tests/test_codex_bridge_contracts.py tests/test_vision_policy.py tests/test_agent_runtime.py tests/test_config.py -q`
- Run new migration tests and `tests/test_vision_migration_compatibility.py` against an owned fixture DB, never the running application DB.

Cover all identity mismatches, unknown fields, path-like IDs, invalid model, oversized data, future/expired deadlines, stage/output mismatch and consent confusion. Test old stored policies with missing new fields; enabling DOM-only Codex without image consent must succeed while Gemini retains its existing rule. Verify migration upgrade from current head, existing null snapshots and scoped FK/uniqueness. Leave execution v1 schema/fixtures unchanged.

Acceptance: contracts and pure rules pass offline; no job is created or CLI called; no existing tenant is auto-enabled.

## Risks and non-goals

Do not mislabel filesystem paths as secret storage or use raw tenant strings as directory names. Derive path components from validated UUIDs/hashes. This phase defines metadata, not a public job-management API or a replacement authentication system. The ADR records the user decision and proposed technical limits; it does not authorize production use.
