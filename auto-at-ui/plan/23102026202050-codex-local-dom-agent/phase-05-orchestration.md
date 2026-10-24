# Phase 05 — v4 orchestration, durable fencing and safe progress

Status: **completed**. Started: 2026-10-24 12:54 +07:00. Completed: 2026-10-24 13:16 +07:00. Dependencies: phases 1–4.

## Completion record

Implemented provider readiness, immutable DOM/image consent and confirmation hash,
v4-only submission/reload, capability negotiation, DOM observations, shared call
reservations, durable registration/receipt transitions/finalization, and safe
progress. DOM bindings survive the BFS queue and restoration into worker prepare.
Image escalation uses the retained after-frame captured with the verified checkpoint,
not the live-preview time cache. The private job stores only observation hash/count;
typed text and DOM bodies are absent from proposal/job metadata.

The producer polls policy and session fencing every 200ms and refreshes the short
authorization receipt every two seconds. Cancellation publishes a marker, records
terminal metadata and waits up to five seconds for consumer-owned cleanup. Missing
cleanup acknowledgment emits `bridge_cleanup_pending`; it never revives a job.
Recovery cancels outstanding metadata and does not recreate the memory-only queue.

Added paths:
- `apps/control-plane/infrastructure/persistence/codex_bridge_repository.py`
- `apps/control-plane/infrastructure/vision/codex_composition.py`
- `migrations/versions/d1e2f3a4b5c6_codex_observation_summary.py`
- `tests/test_codex_bridge_repository.py`
- `tests/test_codex_exploration_integration.py`

Changed paths:
- `apps/control-plane/application/{vision.py,vision_reload.py,vision_policy.py,vision_trace_events.py,codex_bridge.py}`
- `apps/control-plane/api/v1/{dependencies/vision.py,routes/vision.py}`
- `apps/control-plane/infrastructure/{codex_bridge/spool.py,vision/codex_batch.py,persistence/models.py,persistence/vision_unit_of_work.py,workflows/vision_publisher.py}`
- `apps/control-plane/domain/{activity.py,codex_bridge.py,entities.py,ports.py,vision.py}`
- `packages/contracts/src/auto_at/contracts/codex_bridge.py`
- `tests/{test_codex_model_batch.py,test_codex_bridge_service.py,test_vision_provider_submission.py,test_vision_policy.py,test_vision_policy_routes.py,test_vision_policy_persistence.py,test_vision_progress.py,test_vision_migration_compatibility.py,test_vision_handoff_repository.py}`
- `tests/fixtures/codex_bridge_fake_cli.py`

Validation (all synthetic; application DB untouched):
- `uv run pytest tests/test_codex_bridge_repository.py tests/test_codex_exploration_integration.py tests/test_vision_provider_integration.py tests/test_vision_locator_pipeline.py -q --basetemp .pytest-artifacts/codex-phase5-integration02 --tb=short`: **47 passed**, including migrated PostgreSQL, real local browser, pinned fake subprocess, both legacy/v4 Gemini paths and approval/deterministic execution/report provenance.
- After replacing preview pixels with checkpoint evidence and exposing cleanup timeout:
  `uv run pytest tests/test_codex_exploration_integration.py tests/test_codex_model_batch.py -q --basetemp .pytest-artifacts/codex-phase5-final07 --tb=short`: **15 passed**.
- Added stale-binding-after-restore case: `uv run pytest tests/test_codex_exploration_integration.py -k stale_binding -q --basetemp .pytest-artifacts/codex-phase5-stale09 --tb=short`: **1 passed**, seven deselected. Rejected second target produced no `/b` visit and no coordinate fallback.
- Policy/submission/reload/activity/contracts/candidate run (`codex-phase5-final05`): **188 passed**. Follow-up submission/reload/writer-rollback run: **37 passed**, one migration-head assertion failed because the additive observation migration changed the head. Updated that assertion; `uv run pytest tests/test_vision_migration_compatibility.py tests/test_vision_handoff_repository.py -q --basetemp .pytest-artifacts/codex-phase5-migration08 --tb=short`: **7 passed**.
- Earlier policy/API/migration/service run (`codex-phase5-api04`): **130 passed**. Initial API tests required updating comparisons to exclude the new read-only consent fingerprint; the corrected runs above passed.
- Rebuilt Linux bridge image and ran contract/spool/process/service/candidate/batch/settings tests with `--network none`, non-root/read-only/cap-drop/seccomp flags: **135 passed**, no skips. Windows transport-only run had **71 passed, one symlink skip**; Linux covers that check. Final image rebuild/regression remains phase 07 after all UI/runtime edits.
- `uv run ruff check .` and `uv run python packages/contracts/export_vision_worker.py --check` passed. Execution v1 has no diff.

Reconciliations: phase 01 metadata lacked the explicitly planned observation
hash/count, so an additive nullable migration was added instead of rewriting the
completed migration. Submission composition moved out of its HTTP route into the
dependency/application boundary. Existing Temporal publication already delegates
v4 work through `vision_publisher.py`, so `temporal_worker.py` needed no edit.
`vision_operations.py`, legacy repositories, fixture ports, and general generation
providers also needed no behavioral changes. The Windows end-to-end fixture uses
an explicitly pinned synthetic Python subprocess; production Linux process-group
ownership remains separately covered by the container tests. No real inference,
tenant enablement, application migration, production deployment or auth change.

## Objective

Wire Codex into new v4 explorations without exposing filesystem/process work to HTTP routes, bypassing consent or weakening the existing operation ledger.

## Exact paths

Add:
- `apps/control-plane/infrastructure/persistence/codex_bridge_repository.py`.
- `tests/test_codex_bridge_repository.py`, `tests/test_codex_exploration_integration.py`.

Change:
- `apps/control-plane/application/vision.py`, `apps/control-plane/application/vision_reload.py`, `apps/control-plane/application/vision_policy.py`, `apps/control-plane/application/vision_model_batch.py`, `apps/control-plane/application/vision_trace_events.py`, `apps/control-plane/application/vision_operations.py`.
- `apps/control-plane/application/codex_candidates.py`, `apps/control-plane/application/codex_bridge.py` (from phases 3–4).
- `apps/control-plane/infrastructure/vision/model_batch.py`, `apps/control-plane/infrastructure/vision/codex_batch.py`.
- `apps/control-plane/infrastructure/persistence/vision_unit_of_work.py`, `apps/control-plane/infrastructure/persistence/repositories.py`.
- `apps/control-plane/infrastructure/workflows/vision_publisher.py`, `apps/control-plane/infrastructure/workflows/temporal_worker.py`.
- `apps/control-plane/domain/activity.py`, `apps/control-plane/domain/vision.py`, `apps/control-plane/domain/ports.py`, `apps/control-plane/domain/entities.py`.
- `apps/control-plane/api/v1/routes/vision.py`, `apps/control-plane/api/v1/dependencies/vision.py`.
- `tests/test_vision_provider_submission.py`, `tests/test_vision_policy_routes.py`, `tests/test_vision_policy_persistence.py`, `tests/test_vision_reload.py`, `tests/test_vision_progress.py`, `tests/test_activity.py`, `tests/test_vision_locator_pipeline.py`.
- `tests/vision_trace_fixtures.py` for compatible fake ports.

## Detailed orchestration

1. Inject a readiness port into VisionPolicies, a job repository into Codex candidate orchestration and the spool adapter into the Codex batch. Construct them in workflow/API composition, not in domain or routes.
2. Extend existing provider/policy/submit/reload response/request schemas with `codex_cli`, the Codex input-policy object, safe readiness fields and an input-policy fingerprint. Codex submit/reload requires expected provider/model/input-policy fingerprint to prevent stale modal consent. Old clients/providers retain existing behavior.
3. Submission freezes input consent/mode/limits, model and prompt version on the new session. Require v4 for Codex. Do not reinterpret legacy historical sessions or select Codex on behalf of existing Gemini sessions. Reload creates a new explicit policy-bound session.
4. Scope the host bridge to the configured tenant and bind it to provider/model. Check current heartbeat, protocol compatibility and login status before claiming readiness; model access can remain unverified until tested. Do not store user identity, credential paths or local executable paths in public provider responses.
5. After a committed browser operation/checkpoint, request a fresh stable DOM observation using its fingerprint and current fencing identity. Record the accepted snapshot ID/hash/count (no body). Dispatch to Codex through the existing bounded application await and retain normal lease renewal.
6. Register job metadata transactionally before publishing files. Commit queued/claimed/running/completed transitions in short transactions when verified receipts arrive. A job with a stale session fence cannot progress, even if files look valid. On metadata/file publication failure, mark a safe terminal failure; do not duplicate a CLI launch.
7. Recheck live policy/session/fence at least once per second while a job is queued/running; renew the short authorization receipt with an expiry capped by session deadline. Revocation or cancellation atomically publishes cancel and awaits bridge cleanup acknowledgement within the bounded shutdown budget.
8. Include every real CLI invocation (DOM and image) in session max-steps and rate accounting. Both stage transitions call the same reservation mechanism. Preserve legacy accounting for existing HTTP adapters and their prior retry behavior.
9. Accept a final response only when scope/job/hash/stage/snapshot/model/sequence match and current policy, session and deadline still permit it. Validate all candidates before recording. Persist only safe action fields plus trusted target binding in the new nullable proposal binding field.
10. Carry DOM binding through the BFS queue and after branch restoration. Extend `primitive()` so explore click/type requests include the observation/element reference and expected descriptor. Worker re-resolves the current target under the same state; never discard the binding and use a bare coordinate as a fallback.
11. Keep before/after captures, target-neutral execution contracts, confirmed-click evidence, immutable handoff and draft approval intact. Job completion is not test success. Unknown worker outcomes still stop; model output cannot mark operations completed.
12. Add safe progress stages `codex.queued`, `codex.started`, `codex.image_requested`, `codex.validating`, `codex.completed`, `codex.failed`. Allow only job UUID, state/call sequence, mode, counts, elapsed milliseconds and safe reason. Use deduplication keys including job/stage. Detailed raw CLI JSONL never enters ActivityEvent.
13. API/workflow restart does not revive an old browser session. Mark outstanding old-fence jobs cancelled/interrupted, reconcile retained evidence and stop per current recovery rules. An already committed response may be inspected for audit but must not launch a fresh action after terminalization.
14. Acknowledge accepted/failed result to trigger spool cleanup. Durable rows survive payload deletion under existing metadata retention. Cleanup and UI errors remain explicit.

## Contract/API and migration impact

Phase 1 migration provides session input snapshots, proposal target bindings and job metadata. This phase adds repository behavior and API projections. No raw DOM/image/job path endpoint is added. `apps/control-plane/main.py` remains composition-only; no new business logic there.

All exported status/failure additions must be allowlisted in domain/API/frontend together. Retain legacy policies and history readers while preventing Codex submission to old/legacy workers.

## Tests and validation

Run focused policy/submission/progress/reload unit and route tests:
- `uv run pytest tests/test_vision_provider_submission.py tests/test_vision_policy_routes.py tests/test_vision_policy_persistence.py tests/test_vision_reload.py tests/test_vision_progress.py tests/test_activity.py -q`.

Then run:
- `uv run pytest tests/test_codex_bridge_repository.py tests/test_codex_exploration_integration.py tests/test_vision_locator_pipeline.py -q` against an owned migrated fixture DB and local fake worker/CLI.
- `uv run ruff check .`.

Required integration cases: DOM observation → queued job → fake CLI → validated unique click → operation evidence → handoff; screenshot escalation; no consent; concurrent duplicate event publishers; stale modal; wrong tenant; result after timeout/cancel; policy change during wait; expired heartbeat; process crash; file publication failure; duplicate receipt; DB failure after response; restart during claimed job; stale binding after BFS restore. Assert no unintended provider call or duplicate physical action.

Run existing Gemini/HF provider integration in the same offline fixture to prove they do not require the host bridge.

## Acceptance and non-goals

A full synthetic Codex v4 exploration produces valid existing trace/locator evidence and safe visible progress. Cross-tenant/stale/late results are rejected. No deterministic verdict, existing session or unrelated provider configuration changes. General generation/reporting still uses its configured provider; this phase does not migrate those agents.
