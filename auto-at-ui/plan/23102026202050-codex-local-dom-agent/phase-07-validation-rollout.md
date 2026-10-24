# Phase 07 — Evaluation, local deployment and rollback

Status: **completed; CLI 0.164.0 isolation qualified; synthetic live DOM canary passed**.
Started: 2026-10-24 13:35 +07:00. Completed: 2026-10-24 19:09 +0700.
Dependencies: phases 1–6 completed; superseded 0.163.0 qualification remains withdrawn.
Offline validation and implementation are ready; no live inference occurred during planning.

## Final completion (2026-10-24 19:09 +0700)

Post-completion deployment follow-up (2026-10-24): the user subsequently authorized
updating the runbook, restarting Docker and committing/pushing. Default Compose
images were rebuilt, the existing database backed up, both Codex migrations applied,
and the application stack started with retained volumes. API/dashboard IPv4 checks,
worker-to-benchmark HTTP and RustFS bucket access passed. The benchmark fixture now
uses `benchmarks/targets/web-ui/Dockerfile` instead of a D: bind mount rejected by
Docker Desktop. Updated `README.md`, `docs/codex-local-bridge.md`,
`docs/vision-agent-operations.md`, `docker-compose.yml` and `.gitignore` document
startup/preview and exclude generated test artifacts. Ruff, staged whitespace,
35 provenance/contract checks and the dashboard production build passed. The full
872-test result below remains the final application-code regression; this follow-up
changes documentation and benchmark packaging only. Existing artifact-retention
fails with a missing `SqlAlchemyArtifactRepository.list_expired` method; this is
outside the feature changes and remains a known operational issue. Codex tenant
activation and live image transfer remain off. Historical no-deployment statements
below describe the earlier evaluation, before this explicit restart request.

The user's "find the way to do" request was resolved by testing schema delivery.
Credential-free capture of the actual canary request confirmed the task, 15 DOM
elements and enabled bound target were present. A bounded diagnostic moved the
identical response schema into prompt text and removed CLI `--output-schema`;
it verified one real DOM action in 8.890s. The integrated normal bridge, prompt
v6, independently passed the same canary in **9.156s, 1 call, 0 images, 1 verified
action**. No stop was rewritten into a click. The provider-internal reason for
earlier safe stops is not established; the tested delivery change resolves this
synthetic gate. Requested model remains Luna; actual-model events are unavailable.

Final implementation paths for schema delivery:

- `apps/control-plane/agents/prompts/codex_exploration.py` and its `README.md`:
  centralized v6 bare-JSON/schema guidance and prompt version.
- `apps/control-plane/application/codex_bridge.py`: append verified schema bytes.
- `apps/control-plane/infrastructure/codex_bridge/process.py` and `doctor.py`:
  remove CLI output-schema argument/requirement; keep isolated YOLO and zero tools.
- `packages/contracts/src/auto_at/contracts/codex_bridge.py`: require context for v6.
- `tests/test_codex_bridge_service.py`, `tests/test_codex_bridge_process.py`,
  `tests/test_codex_bridge_contracts.py`, `tests/test_codex_model_batch.py`,
  `tests/test_vision_provider_submission.py`, `tests/fixtures/codex_bridge_fake_cli.py`,
  `tests/fixtures/codex_bridge_tool_probe.py`: verified-schema prompt wiring,
  strict malformed/extra-field rejection, version and real wire assertions.
- `benchmark/vision/codex/manifest.json`, `validation-20261024.json`, `README.md`;
  root `README.md`, `docs/codex-local-bridge.md`, `docs/adr/010-codex-local-dom-agent.md`,
  `docker/codex-bridge/README.md`, and plan README/phases 03/07: provenance and results.

Final validation:

- `uv run python benchmark/vision/codex/run_offline.py -q --tb=short`: **872 passed,
  2 skipped**, 370.31s (harness 374.064s). Safe aggregate report:
  `.pytest-artifacts/codex-offline-897fb84c30b1.json`. Owned isolated PostgreSQL
  migrations and fake DOM/image approval/deterministic reruns passed. Configured
  application-stack workflow remains excluded because it can mutate/call providers.
- `uv run pytest tests/test_rustfs_operation_storage.py -q --tb=short --basetemp
  .pytest-artifacts/codex-final-rustfs-retry-20261024`: **2 passed**, 5.60s. These
  are the two tests skipped without Docker inside the offline image. First host
  attempt had 1 pass/1 concurrent-writer connection reset; fresh retry passed
  without code changes. This intermittent external-service failure is recorded.
- `uv run ruff check .`, `npm.cmd --prefix apps/dashboard run typecheck`,
  `npm.cmd --prefix workers/playwright run typecheck`: passed. Worker generation
  remains stable; execution v1 has no diff. `git diff --check`: passed.
- After updating the final manifest/evidence, `uv run pytest
  tests/test_codex_bridge_benchmark.py::test_offline_manifest_provenance_and_explicit_live_boundary
  tests/test_execution_contract_fixtures.py tests/test_vision_contracts.py -q
  --tb=short --basetemp .pytest-artifacts/codex-v6-final-provenance-20261024`:
  **35 passed**, 0.44s.
- Bridge and normal canary images rebuilt. All three real-CLI fake-provider wire
  probes pass with `schema_in_prompt_only=true`, YOLO permissions, zero declared
  tools and no injected execution. Hardened existing-login offline doctor passes.
- Normal `run_live.py --confirm-live-dom --auth-file <existing-auth.json>` passes;
  safe report `.pytest-artifacts/codex-live-029f1f1b80b1.json` (3,551 input / 82
  output tokens). Earlier controlled diagnostic report:
  `.pytest-artifacts/codex-live-f295f6f29a25.json` (3,560 / 82).
- Prior unchanged UI evidence is retained: 43 unit tests, 47 mocked browser tests,
  dashboard production build and 55 worker browser tests passed in phases 02/06.
  They were not rerun for the Python-only v6 fix. All owned containers removed.

Deviations and limits: user-authorized Linux container replaces native Windows
execution; CLI pin is 0.164.0 with immutable zero-tool metadata; user-authorized
YOLO makes the hardened outer container the isolation boundary. Schema delivery
uses prompt text and strict local validation instead of provider constrained
output. JSONL cannot expose every rejected unknown tool attempt. One synthetic
normal-path success does not establish general site quality. Image canary remains
explicitly unverified/disabled, as allowed by the release gate. Cumulative live
history is 13 invocations, 10 completed usage reports, 2 verified actions, 0 images;
77,503 input / 353 output tokens, 7,808 cached input. Three historical aborted
calls lack usage. No cost estimate or actual-model identity is inferred.

All seven phases are complete. Activation/rollback are prepared and documented;
no application deployment, migration, restart, tenant enablement, account/model
switch or image-consent change was performed. No next implementation phase.
The records below are historical and superseded by this completion record.

## User-authorized YOLO revision (2026-10-24 18:45 +07:00)

User request: "use --yolo for codex cli in isolation". Implemented `codex exec
--yolo` in the fixed container command. This explicitly supersedes the prior
requirement that the CLI's inner read-only/no-network sandbox remain active.
Luna, existing login, zero-tool catalogue, v5 prompt, schema, consent and independent
Playwright verification are unchanged. CLI permission messages now report
`danger-full-access`; full wire probes still find zero callable model tools.
Injected function/custom calls execute nothing; custom exec remains unsupported.
The existing JSONL limitation for rejected unknown calls remains documented.

Doctor now verifies non-root, read-only root, no effective capabilities,
no-new-privileges and seccomp before CLI/auth checks. A correctly hardened
credential-mounted container passes offline doctor. A container lacking the
hardening fails closed before auth. Existing inner sandbox probes remain fallback
profile compatibility checks, not a claim about effective YOLO permissions.
The trusted CLI can read the read-only credential mount for authentication;
YOLO does not hide it from arbitrary container processes. Model tools stay disabled.

Changed: `apps/control-plane/infrastructure/codex_bridge/{process,doctor}.py`,
`tests/test_codex_bridge_{process,qualification}.py`,
`tests/fixtures/codex_bridge_tool_probe.py`, `benchmark/vision/codex/live_canary.py`
(explicit mode/version provenance), manifest/evaluation record and runbook/ADR/plan.
No prompt text or execution v1 change.

Validation: `uv run python benchmark/vision/codex/run_offline.py
 tests/test_codex_bridge_qualification.py tests/test_codex_bridge_process.py
 tests/test_codex_bridge_benchmark.py tests/test_codex_bridge_service.py
 tests/test_codex_bridge_end_to_end.py -q --tb=short`: **61 passed, no skips**,
43.73s. Earlier host focused run: 30 passed, 12 Linux-only skips. Ruff passed.
All three real-CLI/fake-provider probes pass with `yolo_permissions_sent=true`:
valid schema response, injected function call, injected custom call. Doctor passes
in the hardened container and rejects the unhardened control. Docker's first build
hit a missing extraction snapshot; a retry succeeded without pruning/restarting
application services. Both bridge and canary images rebuilt successfully.

One authorized bounded DOM live trial used 0.164.0/v5/YOLO: **11.083 seconds**,
3,345 input / 24 output tokens, `stop/no_safe_action`, **zero verified actions**,
zero image calls. Thus YOLO is implemented but does not resolve live action quality.
Phase 07 remains incomplete. Cumulative history: 11 invocations, 8 completed
responses with usage; 70,392 input / 189 output tokens, 7,808 cached input. Actual
model events and 3 historical aborted-call usage remain unavailable.
No application migration/restart, tenant enablement, image consent change or
model/account switch. Owned qualification/test/canary containers are removed.
The earlier non-YOLO records below remain historical evidence.

## Authorized CLI revision and current result (2026-10-24)

The user replied "yep, check it" to revising and requalifying the pin. Latest
stable npm metadata selected container CLI 0.164.0. Offline 0.159.3 and unmodified
0.164.0 still declared four tools; 0.151.0 rejected current strict configuration.
No older version or alpha is selected. The native host installation is untouched.

Bundled Luna metadata specifies `tool_mode=code_mode_only`, overriding feature
flags. The image now builds an immutable single-model catalogue from its own
binary, changing only `tool_mode=null`, `apply_patch_tool_type=null` and
`experimental_supported_tools=[]`. Input-request tools are separately disabled.
Doctor compares all catalogue fields against the pinned binary's expected
transformation before any login check, and verifies the centralized immutable
proposal instructions. Missing/modified files or a different CLI fail closed.

Full wire probes inspect both tool declaration surfaces. Valid schema response,
unsolicited function and custom-call probes all exit 0, with no declared tools
or marker writes. Custom exec returns unsupported. JSONL still hides that rejected
unknown call and accepts the final message; this is a documented audit limitation,
not proof that attempts are visible. No callable tool authority is exposed.
Filesystem, credential/proc-read denial, write denial, sandbox network denial,
Windows/Docker atomic publication and cross-container locking pass. Offline
real-login doctor reports authenticated/capabilities-qualified, model unverified.

Three bounded single-call DOM canaries used the existing account and requested
Luna, without image transfer or retries: v3 stop/complete (8.589s); v4
need_screenshot (7.883s, denied by missing image consent); v5 stop/no_safe_action
(7.833s). Zero live actions verified. An offline actual-canary inspection confirmed
15 DOM elements, the enabled Toggle modal button and task in the supplied prompt.
Wire inspection found two bundled coding instructions ahead of the user prompt.
v4 added centralized developer instructions; v5 replaces bundled instructions
using an immutable model-instructions file from the same prompt module. Neither
prompt change is claimed to fix quality. v5 retains all candidate/stop/escalation
options and validation; no response is coerced into an action.

Changed paths for this revision:
- `apps/control-plane/infrastructure/codex_bridge/{catalogue,process,doctor,spool}.py`.
- `apps/control-plane/{domain,application}/codex_bridge.py` (one shared CLI version).
- `apps/control-plane/agents/prompts/{codex_exploration.py,README.md}`.
- `packages/contracts/src/auto_at/contracts/codex_bridge.py` (v4/v5 context required;
  old versions remain readable; deterministic execution v1 untouched).
- `docker/codex-bridge/{Dockerfile,container.py,qualify.py,check_mount.py,README.md}`,
  `docker-compose.codex.yml`.
- `benchmark/vision/codex/{live.Dockerfile,run_live.py,manifest.json,README.md,
  validation-20261024.json}`.
- `tests/fixtures/codex_bridge_tool_probe.py`,
  `tests/test_codex_bridge_{qualification,process,contracts}.py`,
  `tests/test_codex_model_batch.py`, `tests/test_vision_provider_submission.py`.
- Root README, `docs/{codex-local-bridge.md,adr/010-codex-local-dom-agent.md}`,
  this phase, phase 03 correction and canonical plan README.

Validation:
- `uv run python benchmark/vision/codex/run_offline.py -q --tb=short`:
  **857 passed, 2 RustFS skips**, 391.05s. Before the v4/v5 prompt-delivery changes.
  Configured-stack workflow excluded; separate RustFS pass remains historical.
- Final `run_offline.py` with `tests/test_codex_bridge_qualification.py`,
  `tests/test_codex_bridge_process.py`, `tests/test_codex_bridge_contracts.py`,
  `tests/test_codex_model_batch.py`, `tests/test_codex_candidate_service.py`,
  `tests/test_vision_provider_submission.py`, `tests/test_codex_bridge_end_to_end.py`,
  `tests/test_codex_bridge_benchmark.py -q --tb=short`:
  **152 passed, no skips**, 86.54s. Includes v5 and fake DOM/image canary paths.
- `uv run python docker/codex-bridge/qualify.py`, `check_mount.py`: passed.
  `container.py doctor --auth-file <existing-auth.json>`: passed, network none.
- In the read-only image with network none and phase 03's seccomp/tmpfs flags:
  `uv run --no-sync python /app/tests/fixtures/codex_bridge_tool_probe.py`, then
  `--valid-response`, then `--custom-call`: all passed. v5 instructions observed.
- `run_live.py --confirm-live-dom --auth-file <existing-auth.json>` ran exactly
  three times in this revision. Safe reports preserve unsuccessful outcomes.
  Total history: 10 CLI calls, 7 completions reporting 67,047 input / 165 output
  tokens and 7,808 cached input; actual-model events and aborted usage unavailable.

Final source check: 48 qualification/provenance/execution/worker-contract tests
passed (0.54s); Ruff and `git diff --check` passed. Regenerating the worker contract
produced no change, and deterministic execution v1 has no diff. Docker process
listing confirms all task-owned test/canary containers removed; app services remain.
The final post-test edits only normalized test formatting, comments and records.

Remaining blocker and decision: the bounded three-call revision evaluation is
exhausted without a verified DOM action. A new bounded diagnostic budget is needed
for further live investigation. Keep tenant enablement off; image consent remains
absent. Phase 07 and the plan are incomplete. No model/account fallback, application
migration/restart, tenant enablement or deployment occurred.

The earlier 0.163.0 qualification claims below are historical, not current gates.

## Historical blocker and safe remediation (superseded by authorized revision)

The earlier probe inspected only `request.tools`. The pinned CLI also sends tool
declarations under `input.additional_tools`, including nested namespaces. Full
inspection found ten tools with the former arguments, despite disabled feature
flags. Adding `agents.enabled=false` removes six collaboration declarations;
four functions remain (`exec`, `wait`, `request_user_input`,
`request_user_input_async`). `features.goals=false` also removes unnecessary
nested goal guidance. Neither change qualifies tool isolation.

The corrected probe deliberately fails (exit 1) when either tool surface is
nonempty. Against the exact production argument builder, the fake provider
completed a valid schema response (one request) and injected a custom
`functions.exec` call (two internal requests). The latter returned `code-mode
host is disabled` internally, wrote no marker, and was absent from JSONL, whose
final response passed `EventReader`. Feature flags and JSONL alone therefore
cannot establish the planned boundary. A table-form Code Mode host setting was
also tried offline: it still exposed tools and attempted a sandbox-denied write;
that change was discarded. The existing boolean host disable remains in place.
No credential or model service was involved in these tests.

Doctor now checks an explicit code-owned set of qualified CLI versions, currently
empty, and returns `bridge_cli_unsupported` before examining authentication or
starting processes. This prevents deployment from relying on the withdrawn
qualification; it is an intentional temporary availability restriction, not a
successful implementation of the release gate. Tests/fake readiness can still
exercise the remaining application path. No public API or execution v1 change.

Changed paths on this resume:
- `apps/control-plane/infrastructure/codex_bridge/{process,doctor}.py`.
- `tests/fixtures/codex_bridge_tool_probe.py`, new `tests/fixtures/codex_bridge_wire.py`.
- `tests/test_codex_bridge_process.py`, new `tests/test_codex_bridge_qualification.py`.
- `benchmark/vision/codex/{manifest.json,README.md,validation-20261024.json}`.
- `README.md`, `docs/codex-local-bridge.md`, `docs/adr/010-codex-local-dom-agent.md`,
  `docker/codex-bridge/README.md`, and plan README/phases 03/07.

Validation: host focused tests passed 23 with 12 Linux-only skips. The rebuilt
bridge's focused Linux suite passed 121 with no skips in 7.64 seconds. Corrected
real-CLI wire probes fail qualification as expected, rather than being counted as
passing tests. Final offline regression/provenance validation is recorded below
when complete. Earlier full-suite/UI/browser results remain historical; they do
not establish this CLI's tool isolation. No further live calls were attempted.

Required decision: authorize changing the explicitly pinned CLI version and
requalifying it while keeping account/model/consent/sandbox boundaries unchanged.
No replacement version has been chosen. The skill requires direction for a
material scope/prerequisite revision; this is not a request to relax isolation.
Live DOM action quality remains independently unresolved. Image consent remains
absent. Phase 07 and the overall plan must not be marked complete.

Final resume checks:
- `uv run python benchmark/vision/codex/run_offline.py
  tests/test_codex_bridge_qualification.py tests/test_codex_bridge_process.py
  tests/test_codex_bridge_service.py tests/test_codex_bridge_spool.py
  tests/test_codex_bridge_contracts.py tests/test_config.py
  tests/test_codex_bridge_benchmark.py -q --tb=short`: **131 passed, no skips**,
  19.40 seconds (harness 21.187 seconds). Credential-free, loopback-only owned
  PostgreSQL/browser fixtures; includes fake canary and manifest provenance.
- `uv run ruff check .`: passed. `git diff --check`: passed. Execution v1 has
  no diff. Full Python/UI/browser suites were not repeated for this blocked
  qualification fix; their earlier results are retained, not claimed current.
- `docker build -t auto-at-codex-bridge:0.163.0 -f
  docker/codex-bridge/Dockerfile .`: rebuilt with the fail-closed doctor.
- In that image with phase 03's credential-free `--network none` qualification
  flags: `uv run --no-sync python /app/tests/fixtures/codex_bridge_tool_probe.py
  --valid-response` and the same command with `--custom-call`: expected exit 1
  because four tool declarations remain. Synthetic response parsing succeeds;
  the custom call is rejected internally but accepted final JSONL hides it.
- Same credential-free image/flags, `uv run --no-sync python
  /app/apps/control-plane/codex_bridge_cli.py doctor`: expected exit 1 with
  `capabilities_qualified=false`, `failure_code=bridge_cli_unsupported`.
  The bridge and canary images were rebuilt with this gate; no credential was
  mounted and no live-canary invocation was made.

Evidence is also saved in `benchmark/vision/codex/validation-20261024.json`.
No application service or tenant setting changed; owned test containers removed.

Reference: the official [Codex configuration schema](https://learn.chatgpt.com/docs/config-schema.json)
documents `agents.enabled` separately from the multi-agent feature flags. The
actual tool and JSONL findings above are measured with the pinned local binary.

The canonical README's user-authorized Linux container revision supersedes this
phase's original native-host/no-credential-mount setup. Use the qualified bridge
container with only auth.json mounted read-only, isolated runtime, explicit spool,
and no model-visible credentials. Default deployment remains disabled.

## Objective

Demonstrate the complete path with isolated fixtures, make the host bridge reproducible on Windows, and roll out only to explicitly enabled local sessions.

## Exact paths

Add:
- `docker-compose.codex.yml`: opt-in spool bind mounts/settings for control-plane and temporal-worker only.
- `docs/codex-local-bridge.md`: setup, doctor, operation, limits, stop and rollback.
- `benchmark/vision/codex/README.md`, `benchmark/vision/codex/manifest.json`, `benchmark/vision/codex/run_offline.py`: synthetic evaluation, source hashes and isolated fake-CLI runner.
- `tests/test_codex_bridge_end_to_end.py`, `tests/test_codex_bridge_benchmark.py`.

Change:
- `.env.example`: non-secret bridge settings, disabled default, no API credential.
- `README.md`, `docs/vision-agent-operations.md`, `docs/architecture.md`.
- `benchmark/vision/gehihi/manifest.json` and `README.md` only when shared fixtures/tests changed their declared hashes; preserve historical measurements.
- `tests/test_execution_contract_fixtures.py` only if adding an assertion that the v1 fixture output is unchanged; never rewrite v1 for this feature.
- Canonical plan `README.md` and phase status records when execution actually completes.

## Offline evaluation

1. Create a dedicated PostgreSQL fixture (existing pattern: loopback port 55437), migrate it and use owned test data. Never use the configured app database for destructive tests.
2. Extend the existing offline harness pattern to prevent external networking in child processes as well as Python. Hard-pin a fake CLI for all automated tests; clear inherited auth/provider configuration and ensure the real executable cannot be resolved by the harness.
3. Synthetic manifest covers native/custom role controls, forms without secret values, scrolling, ambiguous targets, changed DOM, unsupported canvas/frame, requested/denied screenshot, missing CLI/login/model, malformed output, prompt injection, duplicate files, bridge restart, policy revocation, timeouts and cancellation.
4. Record fixture/contract/prompt versions, CLI fake protocol version, source hashes, call counts, mode, successful uniquely verified actions, safe rejections, escalation fraction and timings. Record raw data class as synthetic. Do not combine mocked metrics with live quality claims.
5. Verify no DOM-only job includes image bytes/path; escalation is consented and counted; no invalid/late result clicks; failed actions remain failed; current highlight matches actual before-frame evidence.
6. Exercise at least one complete existing handoff/draft approval/deterministic execution flow with fake generation providers as needed. Exploration migration must not secretly migrate or invoke the downstream provider.

## Validation commands

Run focused phase checks first, then one broader offline validation:
- `uv run ruff check .`
- `uv run python packages/contracts/export_vision_worker.py` and confirm generated output is stable on a second generation.
- `uv run python benchmark/vision/codex/run_offline.py -q --tb=short` (new harness wrapping pytest with owned DB and fake process).
- `uv run pytest tests/test_execution_contract_fixtures.py tests/test_vision_contracts.py -q`.
- `npm --prefix apps/dashboard run typecheck`, `npm --prefix apps/dashboard test`, `npm --prefix apps/dashboard run build`.
- `npm --prefix workers/playwright run typecheck`.
- From `workers/playwright`: targeted `npx playwright test` for DOM, locators, operations and mocked dashboard specs.

The repo baseline is `uv run pytest`; run its full suite through the isolated harness. `tests/test_playwright_worker_compose.py` includes a workflow that writes to the configured stack and can invoke its provider: exclude it from the existing user stack, or run it only in an independently isolated Compose deployment with fake providers. Report skipped/unavailable checks explicitly.

## Local Windows setup and activation

1. Resolve a dedicated host spool outside repo/home credential folders; restrict ACL to the signed-in user and the needed Docker Desktop access. Set matching absolute host/container paths via Settings. Document and verify rename/exclusive-claim semantics on that bind mount.
2. Keep current Codex authentication untouched. Run doctor; record actual installed native CLI path/version and supported sandbox settings in the local report, not in tenant-visible metadata. Never copy credentials into spool or containers.
3. Start host bridge explicitly with `uv run python apps/control-plane/codex_bridge_cli.py run` in a foreground terminal, or with a hidden background process if implementing a start helper. No service/autostart installation is implicit.
4. Before replacing containers, check there are no active explorations. Apply additive migration, deploy compatible worker/API/workflow, then dashboard; do not interrupt a live browser session.
5. Apply the opt-in Compose override. Only the spool is shared; auth directory, repository working tree and browser profile are not mounted for Codex. Default compose without override remains usable.
6. In tenant settings select Codex + Luna, accept DOM transfer and enable. Image transfer is independently opt-in. Confirm the chosen bridge tenant matches the account's intended local tenant.
7. Do not re-run old failed session IDs in place. Start a new exploration or use existing Reload to create a new policy-bound session.

## Live canary and release gates

A live canary uses the user's selected account/model and approved synthetic fixture only. During execution, use the existing authorization context for a small bounded validation; obtain direction only if material cost, unsupported account changes or different data/provider is required. Do not enable billing or switch model to make a test pass.

Proposed bound: one DOM-only session and one screenshot-escalation session; each retains max 3 CLI invocations and 120 seconds. Image canary requires its explicit image consent. Record actual account/model availability without exposing account details. If quota/login/model blocks testing, record that blocker and leave capability unverified rather than claiming completion.

Release gates:
- All required offline tests pass and Windows process-tree/sandbox/file semantics are demonstrated.
- DOM canary performs a uniquely verified action without image transfer.
- Image canary either proves consented escalation and validation or remains explicitly unverified/disabled.
- UI shows real stages and retained verified highlight.
- No credential/body leakage, duplicate action or contract regression.
- Actual latency/calls/usage and limitations are recorded; no promised monetary savings without measurement.

## Rollback and cleanup

1. Disable new Codex submissions and revoke new transfer permissions; cancel/drain active jobs and wait for owned CLI processes to exit.
2. Keep compatible readers while retaining safe job/session history. A nullable snapshot and additive job/proposal fields do not require deleting historical records.
3. Before parser downgrade, back up scoped non-secret policy overrides, remove only new Codex fields, select a disabled old-compatible provider setting and clear consent; preserve other tenant configuration.
4. Stop the host bridge, remove opt-in bind mounts, and clean only acknowledged/expired job payloads under verified root. Never recursively delete a computed path without resolving and checking containment.
5. Preserve existing browser/artifact retention and metadata rules. No production data-retention interval is introduced.

## Acceptance and non-goals

The local flow is reproducible and rollback is tested with historical HF/Gemini/Codex sessions. Final report distinguishes offline tests, actual canary results and skipped checks. Update canonical phase status only when its work is complete. No production hosting, multi-user shared-account service, API-key migration, unrelated generation-provider change or automatic suite approval is included.

## Historical initial implementation and validation record (2026-10-24)

Implemented paths:

- `docker-compose.codex.yml`, `.env.example`: disabled-by-default opt-in bridge,
  explicit tenant/UUID/spool, credential mount only on the isolated bridge service.
- `benchmark/vision/codex/{Dockerfile,offline_suite.py,run_offline.py}`: disposable
  PostgreSQL and Python/Node/browser processes sharing a loopback-only namespace,
  no credentials, real CLI, host mounts, application connections or Docker socket.
- `benchmark/vision/codex/{live.Dockerfile,live_canary.py,run_live.py}`: separate
  explicit single-call synthetic DOM canary, qualified read-only auth mount,
  safe aggregate diagnostics, retained-before-ack browser evidence and cleanup.
- `benchmark/vision/codex/{README.md,manifest.json,validation-20261024.json}`:
  versioned source hashes, scenario coverage and separate synthetic/live evidence.
- `tests/test_codex_bridge_end_to_end.py`, `tests/test_codex_bridge_benchmark.py`,
  `tests/test_codex_exploration_integration.py`: real browser/file/SQL exploration,
  pending generated draft, human approval and deterministic v1 execution, plus
  child-network isolation, canary safety and HF/Gemini/Codex policy rollback checks.
- `docker/codex-bridge/rollback_policy.py`: non-mutating review-file preparation;
  preserves other runtime overrides and historical evidence.
- `docs/codex-local-bridge.md`, root `README.md`, `docs/architecture.md`,
  `docs/vision-agent-operations.md`, `docker/codex-bridge/README.md`: qualification,
  explicit activation, rollout order, failure diagnosis, limits and rollback.
- `apps/control-plane/infrastructure/codex_bridge/process.py`,
  `tests/test_codex_bridge_process.py`, `tests/fixtures/codex_bridge_fake_cli.py`,
  `tests/fixtures/codex_bridge_tool_probe.py`: pinned CLI startup-warning handling
  and real-CLI/fake-provider success plus unsolicited-tool qualification.
- `apps/control-plane/agents/prompts/{codex_exploration.py,README.md}`,
  `packages/contracts/src/auto_at/contracts/codex_bridge.py`,
  `tests/test_codex_bridge_contracts.py`, `tests/test_codex_model_batch.py`,
  `tests/test_vision_provider_submission.py`: version `codex-dom-v3` clarifies
  proposal eligibility despite missing DOM coverage and evidence-based stopping.
  v2/v3 both require bounded context; existing v2 history remains readable.

Validation completed so far:

- `uv run python benchmark/vision/codex/run_offline.py -q --tb=short`: 839 passed,
  2 RustFS skips, 389.33 seconds. Configured-stack Compose workflow excluded by
  design. Both RustFS tests subsequently passed with their own disposable
  containers: `uv run pytest tests/test_rustfs_operation_storage.py -q -rs
  --basetemp .pytest-artifacts/codex-rustfs-20261024 --tb=short` (6.72 seconds).
- After the CLI warning fix: isolated benchmark/process/service/end-to-end suite
  passed 40 tests, no skips, in 45.13 seconds. The v3 prompt/context/submission/
  end-to-end run passed 116 tests, no skips, in 83.36 seconds. Final benchmark and
  button-canary checks passed 10, no skips, in 8.00 seconds. Full-suite results
  above predate these focused fixes.
- Dashboard: 43 unit tests, 47 mocked browser tests, typecheck and production build
  passed in phase 06. Worker typecheck and 55 DOM/locator/operation browser tests
  passed. Generated-worker-contract parity, Ruff and `git diff --check` passed.
  Target-neutral execution v1 has no diff.
- Rebuilt pinned bridge filesystem qualification, Windows/Docker file/locking
  checks and offline real-login doctor passed. Real CLI against the fake loopback
  provider declared zero tools, rejected unsolicited execution and completed a
  valid schema response with the exact production argument builder.

Initial canary failures were diagnostic evidence, not live success. Startup first
failed from the fixture image's UID 1001 versus the bridge UID 1000 tmpfs ownership;
this was corrected. Three CLI attempts then stopped on a startup warning emitted
as an `item.error`. Offline reproduction identified the exact disabled-Code-Mode
warning; only that exact pre-turn message is now nonfatal. Unknown errors and tool
events still reject. After the fix, Luna returned valid structured responses and
usage through the existing login, but v2 proposed a safe stop rather than the
required action. User confirmed Luna works in Codex. The v3 prompt likewise returns
`stop/no_safe_action` for navigation and a contrasting native Toggle modal button
task. Offline inspection confirms the intent and enabled target are present.
The last call took 7.468 seconds; no live action was verified. Seven CLI invocations
total include three startup-aborted and four valid structured responses. Only the
four completed calls exposed usage: 43,756 input / 94 output tokens, 7,808 cached
input. Actual-model events and aborted-call usage were not exposed; no monetary
claim is made. See the machine-readable evaluation record for each attempt.

Remaining release blocker: obtain a genuine, independently verified DOM action
from the selected model. Further investigation must remain bounded and preserve
safe stopping; never force the model's stop into a click or substitute a model.
The image gate is explicitly unverified/disabled because image consent is absent.
No fallback model/account, image transfer, application migration/restart or tenant
enablement occurred. Local activation is prepared, not performed; current app
services remain untouched. Owned containers and the dashboard fixture are stopped.
Phase 07 and the overall plan are intentionally **not completed**.
