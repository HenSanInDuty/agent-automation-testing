# ADR-012: Batched Codex page coverage and persistent click evidence

- Status: Accepted for local implementation
- Date: 2026-10-25
- Extends ADR-010; requested to avoid repeatedly clicking Home.

Codex exploration inventories safely identifiable visible controls before asking
for a batch of up to ten independent actions. Sibling actions run before planning
child pages. Stable URL fingerprints and locator descriptors prevent repeatedly
proposing the same target under newly issued DOM element IDs. Every action still
requires fresh deterministic binding verification; model output never authorizes
an unverified click. Existing three-call and 120-second defaults remain in force.
The selected Codex model, consent, redaction, rate limits and no-provider-fallback
policy are unchanged. Prompt codex-dom-v7 is centrally versioned.

Each tenant-scoped state stores a bounded inventory with pending, queued,
completed, rejected or failed controls and proposal/operation references. Counts
describe observable controls, not exhaustive coverage of hidden menus or the
whole site. Queries, fragments and credentials are excluded from persistent page
URLs. Control names use the existing sanitized observation representation. No
raw DOM or form values are added to persistence. Existing tenant evidence
lifecycle applies; this does not choose a new production retention period.

The worker retains exact URLs only in its current in-memory checkpoint session.
It may restore a replayable navigation checkpoint without form controls directly
by URL, then checks the resulting state against the checkpoint. Other cases use
the existing verified back/replay path. Failed restoration stops that branch.
Stored URLs and pending controls remain reviewable after reload; they do not
silently restart a browser or replay interrupted actions after a worker restart.
Old sessions have no invented inventory and require a new session to collect it.

A trusted pointer press on the verified element records viewport coordinates;
the worker publishes them only after the corresponding Playwright click succeeds.
This supports transformed elements without guessing their center. The dashboard
marks the retained before-click screenshot and keeps the latest recorded click
visible. Historical evidence without a point may show the verified target box
only when its operation and originating frame match, with an explicit label.
After screenshots never receive an overlay from an earlier frame.

Inventory writes use the existing fenced short transactions. Trace/export reads
retain tenant authorization. Request/result execution contracts stay at v1;
generated tests still need human approval and deterministic verdicts are unchanged.
Offline evaluation uses synthetic pages: one model batch visits three distinct
links, saves their URLs, restores the source, records transformed click points,
and avoids repeating Home. Unit/API/UI tests cover deduplication, isolation,
partial inventories and historical screenshot evidence. No live-provider score
is implied by these synthetic tests.

Local validation on 2026-10-25: Ruff and worker TypeScript checks pass; the
dashboard production build passes. The full isolated Python run recorded 901
passes, two skips and three stale migration/provenance expectations. Updating
those expectations and rerunning the affected suites produced 22 passes. The
47 worker browser checks pass. Dashboard checks pass across the initial run and
focused reruns after updating the generation-provider fixture and assertions for
the persistent historical preview. Container browser tests use a loopback proxy
so Web Crypto is available, matching the user's localhost origin.

The additive migration and compatible services are running locally. A read-only
browser check of session a171e8b5-1860-44ff-a739-3ef19bb2dfd6 displayed its verified
Home target box with no JavaScript errors. That historical session still has no
inventory or exact click points; no evidence was backfilled and no external site
actions were rerun as part of validation.

Follow-up diagnosis of session 8a5ebe28 (2026-10-25): its original DOM HTTP 422
detail had been discarded, so that historical failure cannot be attributed to a
specific worker code. The transport now retains only closed safe DOM failure
categories. Subsequent live diagnostics exposed state drift after capture and a
late `_blank` popup incorrectly marked `unattributed_popup`. Navigation now needs
800 ms of unchanged state (within the existing deadline). Declared new-tab links
wait for their popup event for at most eight seconds, within the same session
budget; ordinary clicks keep their short popup observation window.
The Terms popup also performs a client redirect that destroys an in-flight DOM
read. A standalone browser probe reproduced this exception. Settling retries
only the destroyed-execution-context read, resets its quiet interval and retains
the original deadline. Other exceptions still fail; no click is retried. The
same live probe settled successfully after this change.

For DOM state drift, the controller may record up to two read-only setup waits
per scan, each with fresh frame/state/checkpoint IDs, before scanning again. The
optional v4 `refresh_observation` field is valid only for this checkpointed wait;
it never bypasses target verification for clicks, typing, restoration or replay.
The worker requires the last known fingerprint, records the actual fresh before
image, and validates that state again before executing the wait. Existing state,
hop, time and model-call limits still apply. Compatible controller and worker
images must be deployed together. Trailing refresh evidence does not remove the
preceding explored branch from the approval handoff. No old verdict or screenshot
is overwritten, no failed click is automatically repeated, and execution v1 is
unchanged.

Focused checks cover delayed hydration, a popup response arriving after 1.2 s,
strict stale-target rejection, successful and exhausted bounded DOM refreshes,
safe transport errors, and retained handoff branches. A live pre-popup-fix run
recorded five distinct menu clicks with exact highlight points and saved URLs;
that is partial coverage, not a claim that external sites or all controls passed.

Bridge follow-up: request-directory validation can race the consumer deleting
`raw-output.json` or a writer renaming `.atomic-*`. Only disappearance of those
transient files is ignored; request inputs, scope, response validation and unsafe
paths retain their checks. Deterministic tests simulate both races. Bridge logs
now distinguish handoff phase and safe parser error categories without logging
model output, document contents, credentials or exception text.
Another live handoff failed with `FileNotFoundError` during progress polling.
Missing progress receipts now yield no events until the next bounded poll;
malformed receipts still fail validation and missing progress cannot authorize
an action or substitute for a validated final result.

A later live bridge log isolated `JSONDecodeError` in the model's final output,
independently of the filesystem races. The proposal service allows one retry of
`bridge_malformed_output` per stage. Each retry creates a new audited job and
reserves from the existing session call/rate/time/evidence budget. It rechecks
state and consent, repeats no browser action, changes no provider, and still
rejects a second malformed result. Six focused cases cover recovery, repeated
failure, exhausted budget, stale state, revoked consent and non-retryable errors.

After five completed menu clicks and six retained page URLs, the next live run
exposed `replay_mismatch`: DOM binding replaces proposal coordinates inside the
worker, while the controller correctly retains the submitted action. The worker
now stores the canonical submitted action separately. Replay must match that
action and the verified descriptor, then reuse worker-owned resolved coordinates
under the existing fresh state/target checks. Three focused browser tests cover
DOM replay, tampered proposal rejection and failed-restoration isolation; the
worker TypeScript check passed again. No old trace is rewritten.

Final live verification: session `54dc4de9-207c-4041-bd29-a886bae1b820`
recorded six completed exploration clicks, one completed replay click and seven
page inventories. A read-only UI check confirmed the target highlight and actual
click marker with no JavaScript errors. The session reached its existing
120-second deadline (`session_timeout`); this is partial coverage, not a claim
that all remaining controls or external pages passed. No limits were increased.

Final focused validation: 49 browser tests passed; 26 spool/batch tests and 38
process/provenance tests passed in the credential-free Linux harness. TypeScript,
Ruff and dashboard build passed. A read-only dashboard check found one target
highlight, one actual click marker and no page JavaScript errors on the retained
Terms operation. Live exploration remains bounded by the original session policy.
