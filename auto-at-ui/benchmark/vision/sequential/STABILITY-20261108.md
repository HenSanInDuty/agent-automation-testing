# Stability continuation, 2026-11-08

The user requested continued work until stable after the previous
[resume report](RESUME-20261108.md). Existing local `codex_cli` / `gpt-6-luna`
policy, consent, target and limits are preserved.

## Changes

See [ADR-021](../../../docs/adr/021-dom-collection-and-heartbeat-timing.md).
DOM grounding now deduplicates locator candidates and performs independent reads
concurrently in bounded batches. Failed observations release retained handles.
Mismatch diagnostics expose only category booleans. Heartbeat freshness includes
elapsed file-read time, retaining the same future/expiry and identity checks.

## Diagnostics

The read-only `vision-capture-probe.ts` visits four viewport offsets, three times
each, without model calls or clicks. Before optimization, 10/12 observations
completed; two correctly rejected interaction drift. After optimization, 10/12
completed; two rejected capture/observation boundary drift. This small sample
does not establish a reliability improvement. DOM collection duration varied by
viewport and execution load, so live pipeline trials remain necessary.

## Live trials

| Session | Model jobs | Browser result | Terminal reason |
| --- | --- | --- | --- |
| `125451d3-df49-40df-bebb-c47d5d45cc8b` | 1 completed, 1 cancelled | Navigate + scroll completed | `bridge_offline` |
| `49d43de2-5322-478c-9619-d0e0128d8925` | 4 completed | 6 operations, no clicks | `bridge_stale_result` |
| `422b4b16-3f68-47f5-a8f2-a7d7c223060f` | 1 completed, 1 cancelled | Full initial viewport scan (7 scrolls), 1 click | `bridge_offline` |
| `24031068-ba88-40ba-9cc5-defff22740be` | 2 completed | 11 clicks completed; next download click failed | `download_unsupported` |
| `685a3d43-c5ab-46a0-af07-852c0976c5f5` | 4 completed | 16 clicks, including a cancelled download; 6 popup closes | `state_restore_failed` |
| `966bae38-11d1-4687-a519-d3a45b1ea8b5` | completed jobs | 9 clicks; final click missing after image | `observed` (incorrectly selected action code; capture failed) |

The first trial exposed a separate readiness issue while the bridge process was
still running. The heartbeat race is independently reproduced by a synthetic
test: a timestamp written during the measured read must be accepted, while a
timestamp after the read and an expired heartbeat must still be rejected.
The historical trial is retained as a failure; its exact filesystem timing was
not captured, so the race is not asserted to be its proven sole cause.

Inspection of the saved user task identified a scope-recognition gap:
`Kiểm tra các nút xem có hoạt động không` was treated as `all`, so the model did
not receive the existing visual-button classification and page-wide interaction
checks included unrelated carousel links. The recognizer now accepts this
explicit button-only functionality question, while rejecting mixed/negated or
extended tasks. The existing `visual_buttons` execution path supplies the correct
scope; no provider/prompt/target or user task was changed.

The corrected scope passed 15 unit cases and a real Chromium/persisted integration
using the exact Vietnamese task. The next live run scanned all initial viewports
without DOM drift but was interrupted by another bridge readiness failure.
Readiness diagnostics now distinguish file-read, freshness and identity failures.
An idle shared-spool probe made 600 reads with zero failures; an idle-only probe
does not cover failure during a model exchange.

The next run passed capture and bridge stages, then reproduced the known download
failure. A 2,000-read heartbeat probe during this run had zero failures. The global
download handler unconditionally poisoned even an attributed active click, and
Chromium's new uncommitted download tab could have URL `:` instead of `about:blank`.
The worker now cancels attributed downloads, records initiation as non-replayable,
closes only those uncommitted tabs and retains source-page evidence. Background
downloads remain rejected. The old blanket download rejection test is replaced
by separate attributed/unattributed tests; the previously failing popup-download
test is retained and strengthened with frame/checkpoint/replay assertions.

The next live trial passed download attribution and bridge stages, then a popup
hydrated after its click capture. Closing it was correctly rejected against stale
evidence. The controller now checks the current popup checkpoint and, only if
changed, records a bounded read-only refresh before closing that same known page.
The source checkpoint stays immutable and must still match before another click.
Refresh consumes the existing state/operation budget; close prepare/execute guards
remain unchanged. A controlled popup fixture mutates only after the click response,
so the persisted integration can assert refresh, close and sibling-click order.

The following trial lost final image evidence after an executed click. Its old
terminal reason incorrectly preferred `observed` over `after_unavailable_reason`.
The controller now reports the capture failure while retaining the actual click,
without replay. Capture diagnostics cover both bracketing state reads and file
publication, exposing fixed categories and attempt counts only. A destroyed
navigation execution context discards that image and retries read-only evidence
inside the existing ten-second budget. Other read errors remain failures. The
historical failure did not include this diagnostic, so its exact cause remains
unproven. Two new Chromium cases and a persisted missing-after-image case passed;
three adjacent capture/restoration cases passed too.

## Validation

- TypeScript typecheck and Ruff passed.
- DOM/readiness: 52 cases passed (the new disposal assertion was corrected to
  check actual disposal and a still-live page, rather than a platform-specific
  disposed-handle error string).
- Bridge service/model batch: 22 passed, one platform-dependent case skipped.
- Operation regression: 57 passed. The previously failing download initiation
  case was excluded explicitly and its assertion was not changed.
- After fixing the actual download path, four attributed/unattributed download
  cases passed three repetitions each (12/12), including popup cleanup and
  before/after frame, checkpoint, cancellation and non-replayability checks.
  The complete Linux operation/DOM/readiness run now includes downloads.
- Linux exposed one additional event-order race: the popup page can appear after
  the download event. Reconcile uncommitted download tabs again after settling,
  and keep source-page capture when the page event precedes its download event.
  Typecheck runs from the full workspace; the runtime image intentionally lacks
  dashboard source imported by a separate dashboard spec. Linux test artifacts
  use `/tmp` because the deployed worker filesystem is read-only.
- The first long Linux run exposed process exhaustion after repeated Chromium
  launches (`Cannot fork`; cgroup `pids.current` later read 213 of 256). The worker
  had no init process. That run was stopped after cascading browser-start failures;
  it is not counted as passing. Enable `init: true`, preserve all resource limits,
  and rerun the full group while measuring post-suite process usage.
- After enabling init, all 112 Linux DOM/operation/readiness cases passed in
  5.5 minutes. Cgroup task usage was 37 before and 50 after the suite, below the
  unchanged 256 limit; the process listing showed no accumulated Chrome zombies.
- The old `visual_navigation` fixture clicked its popup last, so no sibling
  restoration was needed before session cleanup. Place its popup before the
  remaining links and retain the close assertion, adding chronological page-ID
  checks proving close-to-parent precedes the next source-page click.
- The host-wide Python run was interrupted and is not a complete validation:
  it includes configured-stack tests. Use the credential-free offline harness
  for the complete suite. Its source manifest was still on prompt v9; refresh
  current source hashes and prompt v11 without changing historical results.
- Three persisted popup integrations passed: ordinary restoration, a visual
  popup followed by a sibling, and controlled post-click hydration. The last
  asserts a fresh recorded observation on the same popup before closing it.
- The full offline run found legacy Codex integration expectations that called
  two clicks on a many-control page complete. Complete DOM/image flow fixtures
  now contain exactly their two branches. The original mixed page remains a
  separate partial-coverage case, and rejected stale bindings must also retain
  `exploration_coverage_incomplete`. Generation approval/execution assertions stay.
- Full isolated run `.pytest-artifacts/codex-offline-e44a8fb760a4.json`:
  1,026 passed, 16 failed, two Docker-dependent RustFS checks skipped, 889 seconds.
  This includes the passing 47-button flow and popup hydration regression.
  Remaining failures grouped into stale coverage/manifest/migration expectations,
  carousel changes during scroll preparation, and loggers disabled by in-process
  Alembic. Keep this failed run as historical evidence; follow-up results below
  must verify each group. The stale-binding test also assumed every explore
  action had a model binding, which incorrectly rejected controller-owned scrolls.
- Focused follow-up `.pytest-artifacts/codex-offline-e10dae50adb3.json`: 44 passed;
  only the stale-binding fixture still failed. Seven viewport cases passed,
  including one rejected prepare followed by exactly one completed scroll, and
  three rejected prepares followed by zero physical scroll/click actions. All
  worker observability tests passed after the migration logger fix. DOM and image
  generation/approval/deterministic execution flows both passed.
- The stale-binding fixture now separately asserts deterministic scrolls carry
  no model binding. One model batch supplies two proposals; the stale target is
  rejected without a click or another model call. Its old expectation of a second
  model call also failed (`cfed58fba87b`); after correcting that counter, all three
  selected stale-binding/provenance cases passed in 12.16 seconds
  (`.pytest-artifacts/codex-offline-5b4d9b2723d0.json`). Every original failing case
  has now passed in a follow-up; the full 1,044-case run was not repeated.

The prior download and popup regressions remain documented in the resume report;
this continuation does not erase or weaken those assertions.
