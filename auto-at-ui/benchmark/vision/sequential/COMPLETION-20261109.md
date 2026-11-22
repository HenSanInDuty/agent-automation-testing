# Stability continuation, 2026-11-09

Resumed Codex session `01a1ba91-8482-7d03-8d11-cb23515b2d42`, interrupted by
an account usage limit while observing the last live trial. The agentmemory
daemon was unavailable; the exact workspace was matched against the local
session transcript and the previous dated reports.

## Recovered outcome

Live session `d69fc7fa-d35a-42b4-a546-c5919baf9044` eventually stopped
`unavailable/unsafe_replay`. All 62 browser operations completed with after
evidence: 19 clicks, 10 popup closes, two navigations, 15 scrolls, one back and
15 waits. Four model jobs completed. These are exploration observations, not
test verdicts or complete coverage.

The final restore closed a popup but consulted that popup's URL/scroll instead
of the returned page's state. It then replayed navigation and seven scrolls
before discovering a non-replayable click later in the path.

## Changes

[ADR-022](../../../docs/adr/022-popup-return-state-and-replay-preflight.md)
records the fix: retain separate restoration evidence, capture the returned page
when needed, restore its scroll and verify the original checkpoint independently.
Preflight the entire replay path before executing any prefix. Private form
checks, source checkpoints, live target checks and execution contracts stay intact.

The new fixture reproduces the sequence Reveal, Top, Popup, lower Sibling.
It checks exactly one click per target and no replay. A private-form mutation
variant refuses the sibling and stops before any replay. The fixture uses
`window.scrollTo` explicitly; an initial fixture used unqualified `scrollTo`,
which the inline handler resolved on the button and did not move the viewport.
Those two failed development runs are not counted as regression reproduction.

## Validation

- Ruff and dashboard/worker TypeScript checks passed.
- Dashboard model tests: 43 passed.
- Focused persisted Chromium regressions: four passed in 81.38 seconds,
  `.pytest-artifacts/codex-offline-526315cff7ca.json`. Includes the two new
  restoration cases and the existing refresh/hydration popup regressions.
- Full isolated baseline (the recovered code before this turn's changes):
  **1,046 passed, two RustFS skips, zero failures**, 979.30 seconds;
  `.pytest-artifacts/codex-offline-86f46f9620a5.json`. The configured-stack test
  remains excluded by the harness because it can call a configured provider.
- Popup/snapshot restoration/coverage/persistence/handoff/provenance regressions
  (before startup/history follow-ups):
  **80 passed, zero skips/failures**, 692.19 seconds;
  `.pytest-artifacts/codex-offline-3dab1f4b788a.json`. Includes the 47-button flow,
  12-button/15-state fixture, private-form refusal and state-limit reduction.
- Chromium visual-button classification/identity checks: three passed, including
  replacement-node rejection. `git diff --check` passed.
- Startup follow-up initially passed six adjacent cases and failed the permanent
  empty case (`725303c4719a`): setting a stop hint alone did not affect the empty
  inventory's terminal result. The final change explicitly stops incomplete.
  Both delayed and permanently empty cases then passed in 15.46 seconds
  (`.pytest-artifacts/codex-offline-7cf7272e5513.json`), without weakening assertions.
- The subsequent page-batch run passed 27 cases and failed the new delayed-history
  case (`5429a17874ba`). Its checkpoint was already restored, but the controller
  still held the preceding screenshot's fingerprint. Requiring both checkpoint
  and captured fingerprint agreement fixes that race. Both history cases then
  passed (`efbd21ce1739`, 26.849 seconds including harness overhead), with exactly
  one Back, bounded read-only refreshes and no replay. The permanently stuck
  case retains its conservative refusal.
- Final Ruff, manifest provenance and whitespace checks passed. The full
  baseline was not rerun after these focused follow-ups.
- Portable summaries and current source hashes:
  [validation-20261109.json](validation-20261109.json). Baseline and follow-up
  counts are separate runs with overlap, not additive unique test counts.

## Local rollout and live validation

Docker Desktop was initially stopped. Existing local services resumed without
resetting their volumes. There were zero queued/running explorations before the
control plane and Temporal worker were rebuilt/replaced. The existing bridge
was started with the same overlay, mounts, consent and model policy.

Reload `ca56188a-e0e7-4dfb-8559-3fd899165f42` uses the retained Mongchiton
request and `codex_cli` / `gpt-6-luna`, with 20 calls, five calls/minute,
10 hops and 50 states. No generated draft was approved by this continuation.
It completed 26 clicks, 14 popup closes, 11 scrolls, 23 waits and one navigation
(75 completed operations), with zero missing after images and zero replay. It
passed the new close/refresh/scroll/restore sequence at operations 54-57, then
stopped `unavailable/dom_snapshot_limit` with 37 persisted states. This trial
overlapped part of the isolated baseline; timings are not a performance claim.

The snapshot cap was unchanged. The controller unnecessarily recollected v3
bindings even when an equivalent observation had just been captured after an
action. The follow-up reuses such an observation only on the same page, action
revision and state fingerprint, retaining full checkpoint and exact-node gates.
The 12-button/15-state fixture covers this failure without model calls.

Isolated live reload `d8e1598d-6558-46fd-a8c3-26b67517bf6f` started after
all Chromium regressions completed. Both deployed Python services were checked
against the workspace source hash. The existing provider, limits and consent
remained unchanged. It recorded only navigation, a white after image, zero
controls and zero model calls. Its raw state was `completed`, but conclusion
coverage remained `not_established`; it is not a successful live validation.

A separate read-only Chromium probe received HTTP 200 at 313 ms with 70 nodes,
zero body text and zero buttons. At 1,512 ms it saw 540 nodes and 14 buttons;
at 5,400 ms it saw 17 buttons. No clicks/model calls were made by the probe.
The controller now gives an initially empty, non-scrollable viewport at most
two explicit read-only refreshes, retaining all budgets, and stops partial if
it remains empty. Controlled hydration and permanent-empty regressions cover
this startup boundary.

Validation session `83f1c907-50f8-47d7-bdd5-d3f140d184b2` used the same
saved task/provider/consent/limits after the startup fix, without concurrent
browser regressions. It inventoried 47 controls (28 styled links, 15 native,
four custom), completed 20, and retained 27 uncompleted. All 63 operations
completed with no failed, rejected or unknown outcomes; four model jobs completed.
It stopped `unsafe_replay` without replaying any prefix. The returned-page
refresh/scroll restoration succeeded at operations 57-61.

Operation 62 clicked the Events navigation item. Operation 63 completed Back
with a changed URL but an unchanged screenshot still showing Events. This
identified a further asynchronous-rendering boundary; the precise website
timing was not captured. The controller now allows at most two recorded
read-only refreshes after a completed Back, each checked against the original
source checkpoint. Controlled delayed-history and permanently stuck-history
fixtures validate progress and conservative refusal separately.

Final live validation `c8fbd0ea-c2cd-467d-a90e-3fabab39e462` ran after the
history tests passed and both deployed services matched the workspace hash.
It observed 47 controls and completed 27, with 20 remaining. It recorded 36
states, three completed model jobs, 80 completed operations (27 clicks, 18 popup
closes, nine scrolls, 25 waits, one navigation), one rejected restore wait and
zero missing after images. There were no replay operations or unknown outcomes.
The API conclusion is **partial / not_established**, not a passing test verdict.

The last operation stopped `state_restore_failed` because its restore wait was
rejected `state_mismatch` **between prepare and dispatch**. Worker diagnostics
record changed interaction and visual-semantic fingerprints, but unchanged URL,
forms and scroll. The before/after images show the features carousel in motion.
This differs from the controlled stale-history-image race fixed above: preparation
had succeeded, then the live page changed again before dispatch. The diagnostic
does not identify exactly which DOM node changed. No guard was relaxed and no
physical action was retried. Complete Mongchiton coverage remains unresolved.

All live metadata and the final API conclusion are retained in
[live-continuation-20261109.json](live-continuation-20261109.json), without raw DOM,
task text, form values or credentials. The local stack remains running; no
explorations are queued/running. Existing uncommitted work is preserved, and no
commit, push, volume reset, policy increase or generated-test approval was made.
