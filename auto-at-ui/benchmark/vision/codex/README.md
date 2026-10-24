# Codex synthetic evaluation

Status: CLI 0.164.0 tool isolation qualified; synthetic live DOM canary passed.
All observations are synthetic. Offline tests use the pinned fake CLI and cannot
establish real model quality, latency, quota, cost or screenshot necessity. Separate
live calls verified access through the existing login with requested `gpt-6-luna`.
The normal v6 bridge verified a Toggle modal action in 9.156 seconds: one call,
zero images. Earlier safe stops remain recorded below. This is a bounded synthetic
result, not a claim of general site quality. Live image validation is disabled.

Run the isolated suite from the repository root:

```powershell
uv run python benchmark/vision/codex/run_offline.py -q --tb=short
```

The harness builds a locked Python/Playwright 1.50.1 image without Codex or
credentials. It starts a disposable PostgreSQL 17 container with `--network none`
and shares only that network namespace with the test container. Python, fake CLI,
Node and Chromium descendants therefore have loopback access only. No host mount,
provider environment, application service or Docker socket is exposed. Tests check
Python and Node cannot connect externally. Owned containers are removed even after
failure; a safe summary is copied to `.pytest-artifacts/codex-offline-<id>.json`.

Build dependency downloads occur before this isolated runtime. Tests use only
locally installed dependencies and synthetic data. The configured-stack workflow
`tests/test_playwright_worker_compose.py` is excluded because it can mutate the
application and call its configured provider. The isolated browser/SQL tests cover
Codex exploration, existing generation approval, execution v1 and reporting.

`manifest.json` records LF-normalized source hashes, fixture/prompt/contract/model
versions, scenario evidence and expected synthetic counts. The two end-to-end
cases exercise DOM-only (one call, no image, two verified actions) and explicit
consented escalation (two calls, one image, two verified actions), then create a
pending draft, require human approval and run it deterministically. Their elapsed
times and fake token counters are recorded separately from live measurements.
The designed escalation fraction is 1/2 sessions; it is not a quality estimate.

DOM worker fixtures cover native/custom controls, secret-value exclusion,
ambiguous/changed targets, unsupported/truncated observations and scrolling.
Other tests cover malformed/injected output, unavailable bridge/model, duplicate
files, stale identity, restart, cancellation, deadlines and policy revocation.
The dashboard's mocked browser suite checks readiness, independent consent,
stale confirmation, SSE/polling and confirmed highlights on desktop/mobile.

## Validation record

Final v6 regression: **872 passed, 2 RustFS skips**, 370.31s. The two Docker-only
RustFS tests passed separately on a fresh retry (2 passed, 5.60s); the first
attempt had one concurrent-writer connection reset. Ruff, both TypeScript
typechecks, generated-worker-contract parity and diff checks passed. Execution v1
is unchanged. UI/browser/build results below are prior passing evidence for
unchanged sources. Phase 07 and the plan are complete; local activation was not
performed. Safe full-suite report: `.pytest-artifacts/codex-offline-897fb84c30b1.json`.

Schema-delivery revision (2026-10-24): the actual request contained the task,
15 DOM elements and the enabled uniquely bound target. Moving the identical
response schema into prompt text and removing CLI `--output-schema` produced a
successful diagnostic (8.890s, 3,560 input / 82 output tokens), then a normal v6
bridge pass (9.156s, 3,551 / 82). Each used one call, zero images and independently
verified one action. Strict local parsing still rejects fenced JSON and extra
fields. The provider-internal reason for earlier safe stops is not established.
All three wire probes pass with schema present in prompt only, YOLO permissions
and zero callable tools. Offline existing-login doctor passes.

Cumulative live history: 13 invocations, 10 completed responses reporting 77,503
input / 353 output tokens and 7,808 cached input tokens; 2 verified actions and
zero images. Three historical aborted calls lack usage; actual-model events remain
unavailable. No application deployment, migration, restart or tenant enablement.

The following revision records are historical and superseded by v6:

YOLO revision, 2026-10-24 18:45 +07:00: user requested `--yolo` inside isolation.
The fixed command now bypasses the inner CLI sandbox; doctor validates outer
container hardening and the model still has zero callable tools. Full wire probes
confirm YOLO mode, valid structured output and unsupported injected calls. A
hardened container passes doctor; an unhardened control fails closed. **61 focused
offline checks passed**, no skips, 43.73s; Ruff passed. One live DOM call returned
`stop/no_safe_action` in 11.083s (3,345 input / 24 output tokens), zero verified
actions and zero image calls. Phase 07 remains incomplete. Totals now include
11 invocations, 8 completions with reported usage: 70,392 input / 189 output,
7,808 cached input. Historical aborted usage and actual-model events are unavailable.


Earlier authorized revision (2026-10-24 15:30 +07:00):
- CLI 0.164.0, immutable tool metadata override and centralized v5 model instructions
  pass all three full wire probes, filesystem/network denial, Windows/Docker file
  publication/locking and offline existing-login doctor. No native CLI update.
- Full isolated suite: **857 passed, 2 RustFS skips**, 391.05 seconds, before v4/v5.
  Final prompt/contract/process/provenance/end-to-end followup: **152 passed, no
  skips**, 86.54 seconds. The earlier separate RustFS and UI/browser results below
  remain applicable evidence; those unchanged suites were not repeated here.
- Three new one-call DOM canaries: v3 stop/complete (8.589s, 9,747 input / 22 output
  tokens), v4 need_screenshot (7.883s, 10,130 / 25), v5 stop/no_safe_action (7.833s,
  3,414 / 24). Zero verified actions and zero image calls. The task and enabled
  bound Toggle modal button were independently confirmed in the actual prompt.
- v4 added developer instructions; v5 replaces bundled coding instructions through
  an immutable model-instructions file. Neither change is claimed to fix quality.
  Source hashes at that point referred to v5. JSONL still hides rejected unknown custom
  calls, although no tools are advertised and injected calls are unsupported.
- Cumulative history: 10 CLI invocations, 7 completed responses with reported
  usage (67,047 input / 165 output, 7,808 cached input), no verified live actions.
  Actual-model events and usage for 3 historical aborted calls were unavailable.
  More live investigation requires a new bounded evaluation budget; image consent
  remains absent. No tenant enablement, app migration, restart or deployment.

Historical records below retain their original evidence and limitations:

- Resume correction: the original real-CLI probe ignored `input.additional_tools`.
  Complete inspection finds four built-in tools after explicitly disabling agents
  and goals. `--custom-call` receives a disabled-host rejection internally, but
  JSONL conceals the attempt and the event reader accepts the final response.
  Both this probe and `--valid-response` now exit 1 because tools remain declared.
  No marker is written. Doctor fails closed for the current pin before auth or
  process access. 121 focused Linux tests passed; no live call ran on this resume.
  The earlier zero-tools statements below are superseded by this correction.
- Final resume regression: **131 passed, no skips**, 19.40 seconds, through the
  credential-free offline harness; includes qualification/process/service/spool/
  contract/config/benchmark checks. Ruff and diff checks passed. The full suite
  and UI/browser suites below were not repeated for this blocked correction.
- Phase 06: 43 dashboard unit tests and 47 mocked browser tests passed; dashboard
  and worker typechecks and production build passed. No live provider involved.
- Initial phase 07 fixture isolation checks passed; the new end-to-end test stopped
  at draft generation because the exploration-only fixture deliberately had an
  empty execution-origin policy. The end-to-end fixture now explicitly allows its
  own synthetic loopback target; application policy behavior is unchanged.
- Full isolated Python suite: **839 passed, 2 skipped**, 389.33 seconds. The two
  RustFS checks require Docker and intentionally cannot run inside this image;
  both subsequently passed in their own disposable containers (6.72 seconds).
- After the exact CLI startup-warning fix, **40 process/service/canary/end-to-end
  tests passed**, no skips, in 45.13 seconds. The v3 prompt/context/submission checks
  passed **116 tests** in 83.36 seconds, and the final button-canary/benchmark checks
  passed **10 tests** in 8.00 seconds. The full run predates these focused changes.
- Worker DOM/locator/operation browser tests: **55 passed**, no skips. Ruff,
  generated-worker-contract parity and `git diff --check` passed; execution v1
  is unchanged. Existing collection/deprecation warnings remain.
- Rebuilt pinned bridge: filesystem sentinels, Windows/Docker publication,
  exclusive locking, acknowledgement/cleanup and offline real-login doctor passed.
  A fake loopback provider advertised zero tools; unsolicited execution failed.
- Full-run synthetic measurements: DOM 1 call / 0 images / 2 verified actions /
  6.999 seconds; escalation 2 calls / 1 image / 2 verified actions / 8.659 seconds.
  Both resulting drafts required approval and passed deterministic reruns.
  The fake token counters (2/3 and 4/6 input/output) are fixtures, not usage data.
- Machine-readable safe evidence: [validation-20261024.json](validation-20261024.json).

## Live gate

Use only the existing account and selected `gpt-6-luna`, with at most one DOM-only
session plus one separately consented image-escalation session, each at most three
calls and 120 seconds. No billing, model/account fallback or configured-tenant
enablement is implicit. Record model availability, safe failure, actual usage when
exposed, elapsed time and verified browser action count. Missing image consent
leaves that gate unverified and image transfer disabled. An unavailable account or
model must remain a stated release blocker, never an offline success claim.

Historical attempts before v6: on 2026-10-24, three initial invocations stopped on the CLI's
disabled-Code-Mode startup warning, initially misclassified as a tool/provider
error. Offline reproduction against a fake provider identified it precisely. Only
that exact warning before `turn.started` is now nonfatal; changed/mid-turn warnings,
real errors and all tool events remain rejected. The real CLI then completed a
valid schema response against the fake provider with zero tools declared.

Four subsequent live calls returned valid structured responses and usage. The
Branch A navigation task with v2/v3 and a contrasting Toggle modal button task
with v3 did not propose their target. The latest response was
`stop/no_safe_action`, mapped to `canary_expected_target_not_proposed`, in 7.468
seconds. An offline inspection confirmed the supplied intent and enabled target
were present; the worker independently verified fake proposals for both tasks.
The v3 prompt clarifies bound-target eligibility, missing-coverage semantics,
nullable action fields and evidence-based stopping; it has not resolved this
live proposal-quality limitation.

Across all seven CLI invocations, no image was transferred and no browser action
was accepted from the live model. The four completed calls reported 43,756 input
tokens, 94 output tokens and 7,808 cached input tokens; usage for the three aborted
invocations is unavailable, so these are partial totals, not a total cost claim.
The CLI did not expose an actual-model event; requested model and successful
response evidence are recorded separately. No account/model fallback occurred.
An initial zero-call startup probe also caught and fixed the canary-only tmpfs
UID mismatch. The user confirmed Luna works in Codex.

The v6 normal-path result above now satisfies the independently verified DOM
action gate. Image validation remains explicitly unverified and disabled.

Doctor passes the isolation gate. A future explicitly authorized recheck can use
the command below; it makes a real model call. Build the normal bridge and offline
images before this bounded canary:

```powershell
docker build -t auto-at-codex-canary:0.164.0 -f benchmark/vision/codex/live.Dockerfile .
uv run python benchmark/vision/codex/run_live.py --confirm-live-dom --auth-file "$env:USERPROFILE/.codex/auth.json"
```

This runs one call and at most 120 seconds of browser/model work, after offline
doctor qualification. It mounts only auth.json read-only and uses a temporary
job/browser home; the launcher retains only safe aggregate JSON and removes its
owned container. The pinned browser fixture uses UID 1001 (the bridge uses 1000).
The current task is Toggle modal and requires a freshly verified click plus a
changed state fingerprint, with no branch navigation. Prior navigation failures
remain in the results; a safe stop never satisfies the live gate.
