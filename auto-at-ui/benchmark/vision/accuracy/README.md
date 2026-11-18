# Vision accuracy improvement loop

Canonical execution plan: `plan/09112026103202-vision-accuracy-loop/README.md`.
This benchmark does not alter production exploration conclusions or test verdicts.

## Oracle and independent evidence

`oracle-mongchiton-1280-v1.json` retains the independently annotated 47 positive
positions and 14 sampled negative content links from the November 1 dataset.
The November 9 review uses 1280×720, Chromium 133.0.6943.16, matching the deployed
worker. The full-page image and public DOM audit are retained alongside the oracle.
Duplicate labels at distinct positions retain distinct IDs. Responsive positions
and structural paths were refreshed; labels were not changed to fit the classifier.
News labels include their displayed dates; three negative gallery samples are
structurally selected from the moving gallery, not an exhaustive gallery inventory.

The initial audit implementation counted three offscreen/occluded video copies.
`audit-1280-20261109-initial.json` preserves that failed development result.
The visible audit reinstates complete viewport bounds and hit testing. It finds
47/47 positives, no unexpected targets, 47 bound targets, no skipped elements,
and no observation failures. This is **detection**, not verified click accuracy.
Read-only auditing makes no model calls and clicks no external controls.

The next independent audit against the frozen oracle observed 46/47 (97.87%
recall, 100% precision), with video mct-47 missing and no observation errors.
Its strict completeness exit code is 1; the miss is retained, never relabeled.
`baseline-20261109.json` records this detection result and no click-accuracy claim.

Outcome rules are specified before qualification. Navigation must match the
declared destination or an independently reviewed redirect chain. Opening any
popup does not suffice. UI selections must visibly match the selected tab,
character or slide. Autoplay alone does not prove a carousel click worked.
The empty-search rule applies only with an empty input. Video playback must
identify the declared video. Unresolved outcome evidence earns no credit.
Opening a payment/registration landing page never authorizes submitting it.
Downloads are never installed or executed.

## Scoring

`metrics.py` is pure deterministic scoring. It consumes an oracle and adjudicated
operation records; it does not infer correctness from `completed`, HTTP 200,
image difference or the proposing model's answer. The collector must validate
referenced frames and bindings before supplying an evidence-review assessment.

- Coverage: distinct correctly verified positive targets / all oracle positives.
- Accuracy: correctly verified explore click/type attempts / all such attempts,
  including rejected, failed, unknown and unverified attempts.
- Detection: independent annotation precision and recall.
- Every ratio must be strictly above 95%, using integer comparison. Empty samples
  cannot pass. Wait/restore/scroll do not inflate interaction accuracy.
- Any wrong target, unsafe action or unsettled outcome prevents qualification.
- Three consecutive terminal runs of the same source/config/oracle must pass,
  with at least 100 interaction attempts combined. Failed runs reset the streak;
  duplicate session IDs cannot count twice.

The API may still truthfully say partial when this benchmark exceeds 95%.
Business correctness and population-level statistical reliability are not claimed.
The old live baseline has 27/47 runtime-completed controls; its independent
outcome accuracy remains **not established**, pending evidence adjudication.

## Commands

From repository root:

```powershell
uv run pytest tests/test_vision_accuracy_metrics.py tests/test_vision_conclusion.py -q
uv run ruff check benchmark/vision/accuracy tests/test_vision_accuracy_metrics.py
```

From `workers/playwright/`:

```powershell
npm.cmd run typecheck
npm.cmd test -- src/vision-visual-buttons.spec.ts src/fixtures/visual-buttons-audit.spec.ts --workers=1
npx.cmd tsx src/fixtures/visual-buttons-audit.ts --dataset ../../benchmark/vision/accuracy/oracle-mongchiton-1280-v1.json --output ../../benchmark/vision/accuracy/audit-unique-id.json
```

Audit outputs are exclusive-create, never overwritten; choose a fresh path.
All query strings, fragments, credentials and form values are omitted. Public
destination hashes preserve identity without exporting arbitrary query values.
Source hashes and oracle hashes must be frozen again after any behavior change.

## Resumable API harness

`uv run python benchmark/vision/accuracy/run.py --help` lists start, import,
resume, collect and evaluate. Supply a private headers JSON path, never credentials
in an artifact. `start` persists a new iteration/key before any POST; `resume`
submits or polls that same iteration. A timed-out POST must be resumed, not replaced.
`import` reads an existing terminal session and marks it ineligible for qualification.
`collect` exports only allowlisted metadata; optional scoped diagnostic JSON can
identify the mismatch stage. Frames are read through authorized endpoints and
their bytes/length/checksums verified before positive scoring. Outcome reviews
are content-addressed, operation/oracle/frame-bound artifacts, not arbitrary labels.
An OS file lock prevents concurrent writers and is released on process death.

### Quiet monitoring and fresh-session handoff

After submission, monitor the existing session in one process:

```powershell
uv run python scripts/watch_vision_session.py --session <session-uuid> --headers-file <private-headers.json> --timeout 1800
```

The default polls every 30 seconds and prints only a terminal result or error.
Add `--changes` to print state transitions; unchanged polls remain silent.
Output contains only the session ID, state, event and HTTP status. It never fetches
frames, dumps response bodies, submits another run or changes the manifest.
Exit 0 means a terminal state was observed, **not** a passing benchmark; exit 1 is
a read/configuration error, exit 2 is a monitor deadline. The underlying run
continues after timeout or interruption. Use the existing `resume`, `collect`
and `evaluate` commands to persist and adjudicate results after monitoring.

Keep logs/evidence on disk and return short summaries to the assistant. Inspect
at most two relevant images per tool call and retain each independent review.
At the end of each round, update the canonical plan README with the run IDs,
source/config/oracle identity, tests and score, evidence paths, outstanding
processes and exact next command. End the turn there and use a fresh session for
the next round. The assistant does not automatically create a new conversation.

Historical import `51a086ac-8612-4808-8fbe-ca091955f44c` preserves the previous
live failure at operation 81: before_dispatch/state_mismatch during restoration,
with zero missing frames and unchanged partial runtime conclusion. No model call
or browser operation was made by this import. Model-job counts and monetary cost
are not exposed by these result endpoints; phase 04 must attach separately scoped
bridge usage metadata and report unknown cost honestly, never substitute candidate
batch counts for actual model calls.
