# Vision trajectory replay

**Overall status: completed — 2026-09-07 22:07 +07:00.**

## Goal

Turn the Vision Agent's private BFS screenshots into an honest, usable **Exploration evidence** experience: while the agent works, a project reader can see the current state and safe progress; after it finishes, they can follow one selected branch as explicit `before image -> candidate action -> observed after image` transitions and inspect sibling branches without mistaking proposals for executed actions.

## Acceptance criteria

- The UI never calls a BFS gallery an execution replay. It labels the feature **Exploration evidence** and describes every candidate as proposed, attempted, observed, rejected, or terminal.
- Each non-stop candidate has one immutable, tenant-scoped trajectory edge that links its parent state, proposal, child state when captured, safe outcome, duration, and safe terminal/error code. Stop candidates also have an edge/outcome with no child state.
- A running session shows a live current-state card plus connection state and receives newly captured states/edges through the existing authorized activity stream with polling fallback; it does not wait for a terminal session or present guessed browser progress.
- A completed session opens on a deterministic default path: highest cumulative-confidence path among completed/observed edges, with stable sequence/id tie-breakers. Previous/Next, keyboard navigation, thumbnail/scrubber, and branch switching all describe the same selected path.
- One transition renders at a time: a labelled action and at most its one selected coordinate marker appear between its before and after frames. Sibling candidates are shown as alternatives, never overlaid as simultaneous actions.
- Safe diagnostics identify policy/limit/navigation/capture/provider/candidate/draft-handoff outcomes at their affected state or edge. No typed value, raw prompt/reasoning/provider payload, cookies, URL, storage key, screenshot URL, or CDP/debugger endpoint is returned.
- Existing privacy, RBAC, artifact deletion, at-least-once processing, advisory-only behavior, and `TestExecutionRequest`/`TestExecutionResult` remain intact.

## Request and decisions

The request is to improve Vision Agent replay from the 2026-09-07 research and keep the agent's work visually understandable to users in real time.

Confirmed by research:

- The worker intentionally materializes isolated BFS nodes; this is a graph, not continuous video.
- Private frames remain authorized evidence, and execution verdicts and approval boundaries remain unchanged.
- The primary experience is a selected linear path; the tree is secondary diagnostics.

Planning assumptions:

- Reuse the current PostgreSQL/RustFS storage, cookie-authenticated API, `vision` activity/SSE mechanism, and current provider/policy settings. This plan does not select a model, cloud service, retention period, or new browser-session provider.
- Add a versioned **advisory trajectory** contract/API rather than alter target-neutral runner contracts. Existing historical sessions without edges degrade to a clearly labelled legacy **Exploration evidence** state gallery; no fabricated outcomes/backfill.
- Persist only redacted, bounded labels and metadata. URL visibility is represented by a non-reversible URL fingerprint/change classification, because the request and research prohibit exposing target URLs in replay responses.

## Source-scout findings

| Evidence | Current behavior / implication |
| --- | --- |
| `apps/control-plane/application/vision_events.py` | Captures/persists each node before asking the model, adds every non-stop candidate independently to the FIFO BFS queue, and emits safe progress. It has no parent-proposal-to-child outcome record. |
| `workers/playwright/src/vision.ts` | `observeVisualTreeState` opens a new context, navigates and replays ancestors, then captures a screenshot. Sibling isolation makes interpolated video misleading; it currently returns no safe page-result metadata. |
| `apps/control-plane/infrastructure/persistence/models.py` | States contain parent/hop/checksum; proposals only reference originating state; frames reference states. These are sufficient anchors for a new immutable edge table but not transition semantics. |
| `apps/control-plane/api/v1/routes/vision.py` | The replay endpoint joins frames to all originating proposals, so the dashboard cannot identify a child or outcome. Activities already enforce project READ and have SSE plus five-second fallback polling. |
| `apps/dashboard/app/vision-dashboard.tsx` | Loads one blob at a time and overlays all state proposals with the same marker. It has the correct safe progress component but not a path/tree model. |
| `apps/dashboard/app/components/vision-progress-timeline.tsx` | Existing authorized SSE/polling can signal state/edge availability; the UI must refresh the trajectory snapshot atomically on those safe signals. |
| `apps/control-plane/application/vision_replay.py`, `tests/test_vision_replay.py` | Frame reads/deletion are tenant/project authorized and byte-verified; preserve these paths and private/no-store behavior. |
| `packages/contracts/src/auto_at/contracts/vision.py` | Vision already has its own v1 contracts, separate from deterministic execution contracts; the trajectory contract belongs here, not in execution. |

## Constraints and pre-flight boundaries

- Follow `AGENTS.md`: API stays HTTP-only; application orchestrates; domain has no FastAPI/ORM/LLM imports; the dashboard remains a thin client.
- Preserve tenant and project authorization at every trajectory read, frame read, persistence operation, worker request, and activity event. Never use a browser-supplied correlation ID as authorization.
- Recheck policy/origin/limits at execution; isolate fresh worker contexts; preserve checksums, deletion semantics, idempotency, correlation IDs, and cleanup of temporary worker images.
- The LLM stays advisory and untrusted. Keep hostile-image prompt boundaries, strict candidate validation, no hidden browser capability, no raw model content in observability, and the existing human-only generated-draft approval flow.
- Screenshot transfer consent and existing artifact retention/deletion policy apply. The plan adds no provider/model, secrets, retention, cost, or deployment choice.

## Phases

| # | Objective | Status | Dependencies | Validation |
| --- | --- | --- | --- | --- |
| 1 | Define immutable trajectory edges and persistence | completed — 2026-09-07 21:38 +07:00; added immutable redacted edge contract, schema, migration, and idempotent tenant-scoped repository reads | Existing state/proposal/frame schema | Passed Ruff, 9 focused tests, Alembic head, and diff check; database upgrade not run because no local test database was available |
| 2 | Capture safe branch outcomes and live trajectory activity | in progress — started 2026-09-07 21:38 +07:00; worker observation metadata and processor edge lifecycle | Phase 1 | Worker contract/spec and event-processor tests |
| 3 | Publish authorized trajectory reads and build trajectory-first UI | completed — 2026-09-07 22:04 +07:00 | Phases 1-2 | Route/API/model/dashboard unit tests and typecheck |
| 4 | Add representative fixtures, accessibility checks, and guarded rollout | completed — 2026-09-07 22:07 +07:00 | Phases 1-3 | Focused Python/TypeScript suites, Compose scenario where available |

## Risks, rollout, and out of scope

## Execution progress

- **Phase 2: completed 2026-09-07 21:50 +07:00.** The worker tree-observation boundary is now v3 and returns only duration, a SHA-256 final-URL fingerprint, and a URL-change classification. The processor creates a redacted `proposed` edge before a branch queues, then performs its single permitted finalization after a child capture or a safe terminal outcome. New activity stages are `edge.proposed`, `edge.observed`, `edge.failed`, and `edge.terminal`; their metadata is allow-listed and contains no typed values or URLs.
- Changed: `workers/playwright/src/vision.ts`, `workers/playwright/src/vision.spec.ts`, `apps/control-plane/application/vision_events.py`, `apps/control-plane/domain/activity.py`, `apps/control-plane/domain/entities.py`, `apps/control-plane/infrastructure/persistence/repositories.py`, `tests/test_vision_event_processor.py`, and `tests/test_vision_trajectory_repository.py`.
- Validation passed: focused Ruff; focused Pytest (18 passed); worker `npm.cmd run typecheck`; worker `npm.cmd test -- vision.spec.ts` (2 passed); `uv run alembic heads`; and `git diff --check`.
- Deviation: Phase 1's initial insert-or-verify repository behavior could not represent the plan's required proposed-to-observed lifecycle. The immutable proposal identity remains fixed, while a proposed edge now permits exactly one bounded finalization and accepts only an identical replay thereafter. No migration was required.
- **Phase 3: in progress 2026-09-07 21:50 +07:00.** Implementing the authorized trajectory snapshot route and selected-path dashboard; its Phase 2 dependency is unlocked.
- **Phase 3: completed 2026-09-07 22:04 +07:00.** Added an authorized, redacted, coherent trajectory snapshot with a truthful edge-less legacy label; it exposes only IDs, sequence/hop/capture metadata, safe action summaries, confidence, status, duration, and safe outcome codes. The dashboard now fetches that snapshot on safe activity/poll updates and presents a selected path, alternatives, scrubber, keyboard navigation, and an explicitly labelled Exploration evidence view. The older private gallery remains compatible and no longer overlays candidates as simultaneous actions.
- Changed: `apps/control-plane/application/vision_trajectory.py`, `apps/control-plane/api/v1/routes/vision.py`, `apps/control-plane/domain/ports.py`, `apps/control-plane/infrastructure/persistence/repositories.py`, `apps/dashboard/app/generation-types.ts`, `apps/dashboard/app/generation-api.ts`, `apps/dashboard/app/components/vision-trajectory.tsx`, `apps/dashboard/app/components/vision-replay-model.ts`, `apps/dashboard/app/components/vision-progress-timeline-model.ts`, `apps/dashboard/app/vision-dashboard.tsx`, and focused tests.
- Validation passed: focused Python Ruff; `uv run pytest tests/test_vision_routes.py tests/test_dashboard_route_contracts.py` (21 passed); dashboard `npm.cmd run typecheck`; dashboard focused API/model tests (9 passed); and `git diff --check`.
- **Phase 4: in progress 2026-09-07 22:04 +07:00.** Adding synthetic coverage and executing the plan's final validation/rollout checks.
- **Phase 4: completed 2026-09-07 22:07 +07:00.** Added a fully synthetic redacted fixture spanning observed-click, no-change scroll, terminal stop, failed capture, sibling alternatives, and a missing child frame. Updated research/runbook terminology and fallback/deletion guidance. The local Compose stack was healthy and the schema upgrade completed; an end-to-end authenticated submission was deliberately not issued because it requires a user-selected target URL and task intent, which would materially expand this implementation validation into a live provider call.
- Validation passed: `uv run ruff check .`; `uv run pytest --basetemp .pytest-tmp\\phase4` over 42 Vision contract/persistence/processor/replay/route tests; dashboard `npm.cmd test` (22 passed) and `npm.cmd run typecheck`; worker `npm.cmd test -- vision.spec.ts` (2 passed) and `npm.cmd run typecheck`; `uv run alembic heads`; local `docker compose exec -T control-plane uv run --no-sync alembic upgrade head`; and `git diff --check`.
- Rollout order: apply the additive migration, deploy worker/processor writes, enable the authorized trajectory reader, deploy the dashboard, then enable display for authorized tenants. Existing edge-less sessions retain the legacy gallery fallback; API/UI readers can be rolled back without removing trajectory data.

- Migration must be additive and support existing sessions; deploy database schema before code that writes edges, then API/UI readers with legacy fallback.
- A node can fail before a child frame exists. Edges must support `child_state_id = null` and a terminal safe status rather than losing the explanation.
- At-least-once event delivery can replay an edge write. Use an immutable natural key per session/proposal/attempt and reject mismatched duplicates.
- More live frame fetches could increase private-evidence traffic. Fetch only current/selected thumbnails on demand, revoke object URLs, use no-store, and avoid prefetching original blobs.
- Do not create a continuous video, public/shareable session, CDP endpoint, raw image URL, raw URL/title, typed text, cookies, provider/model transcript, chain-of-thought, automatic test approval, or verdict integration.

## Phase files

- [Phase 1 - trajectory contracts and storage](phase-01-trajectory-contracts-storage.md)
- [Phase 2 - observed branch execution](phase-02-observed-branch-execution.md)
- [Phase 3 - live trajectory API and dashboard](phase-03-live-trajectory-dashboard.md)
- [Phase 4 - fixtures, validation, and rollout](phase-04-fixtures-validation-rollout.md)
