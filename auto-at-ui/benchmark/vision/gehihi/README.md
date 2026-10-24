# Gehihi synthetic evaluation

Provider `gemini`; model `gemini-3.8-flash`; prompt `vision-exploration-v6`;
transport `inline_png_mock_http`; fixture version `gehihi-controls-v1`;
Playwright `1.50.1`. All model responses are **mocked**, never real model output.
Execution date: 2026-10-17 (Asia/Saigon). Live canary: **not run**.

The [manifest](manifest.json) records synthetic cases, expected invariants and
SHA-256 hashes of UTF-8 source with LF line endings. The benchmark test checks
those hashes and sends each response case through the actual Gemini adapter and
candidate validator using `httpx.MockTransport`. It never sends a provider request.
The manifest also points to browser/SQL tests; listing a case is not a claim that
the adapter test alone ran a browser or persisted a trace.

## Reproduce safely

2026-10-23 retry maintenance: refreshed the Gemini adapter test hash after adding
bounded HTTP 500/502/503/504 retries. Mocked tests cover recovery, exhaustion,
Retry-After, remaining deadlines, cancellation and safe logs. Authentication,
quota and invalid-output cases still make one attempt. Existing response cases
and expected metrics are unchanged; no live canary is claimed by these tests.

2026-10-23 timeout maintenance: refreshed the Gemini adapter test hash for the
120-second Vision request limit. Mocked deadline tests additionally verify a
35-second response can complete, while requests exceeding 120 seconds or the
remaining session time are cancelled. Response cases and expected metrics are
unchanged; no live provider canary was run for this change.

2026-10-19 click-evidence maintenance: the manifest hash for
`workers/playwright/src/vision-operations.spec.ts` was refreshed after adding
confirmed-click coordinate and before-frame assertions. The response cases and
expected metrics are unchanged. The provider integration hash also reflects a
corrected `origin_after-v4` expectation: existing v4 sessions observe origins
without allowlist gating, while legacy sessions still stop. Current validation is recorded in
[the focused playback plan](../../../plan/19102026043228-agent-focused-web-playback/README.md);
the dated measurements below remain historical results.

Use the repository's uv environment, pinned pnpm and installed Playwright browser.
Use an unused owned fixture port, never the application database on 5432:

```powershell
docker run --rm -d --name gehihi-evaluation-postgres -e POSTGRES_PASSWORD=vision-fixture-only -p 127.0.0.1:55437:5432 postgres:17-alpine
uv run ruff check .
uv run python benchmark/vision/gehihi/run_offline.py -q --tb=short
```

The harness disables Settings dotenv, clears inherited application settings,
sets a synthetic database URL, migrates its own UUID database and drops it in
`finally`. Vision fixtures create additional disposable UUID databases on 55437.
Python sockets reject non-loopback and configured application/provider ports.
Browser workers use their owned loopback fixtures; RustFS tests create disposable
containers. The harness excludes `tests/test_playwright_worker_compose.py` (three
configured-stack tests that can invoke a reporting provider). Do not use plain
`uv run pytest` against your configured stack for this offline gate. The harness
does not sandbox arbitrary subprocesses and is intended for these reviewed tests.

Stop only the container created above when finished:

```powershell
docker stop gehihi-evaluation-postgres
```

For TypeScript and the production dashboard fixture:

```powershell
corepack pnpm --filter @auto-at/dashboard typecheck
corepack pnpm --filter @auto-at/dashboard test
corepack pnpm --filter @auto-at/playwright-worker typecheck
$env:NEXT_PUBLIC_CONTROL_PLANE_URL='http://127.0.0.1:3107'
$env:NEXT_TELEMETRY_DISABLED='1'
corepack pnpm --filter @auto-at/dashboard build
corepack pnpm --filter @auto-at/dashboard start --hostname 127.0.0.1 --port 3107
```

In another terminal (browser API requests are intercepted with synthetic data):

```powershell
$env:VISION_DASHBOARD_URL='http://127.0.0.1:3107'
corepack pnpm --filter @auto-at/playwright-worker test src/vision-dashboard.spec.ts --workers=1
corepack pnpm --filter @auto-at/playwright-worker test src/vision-locators.spec.ts src/vision-operations.spec.ts --workers=1
```

Stop the owned dashboard process afterward. Do not restart application services,
modify `.env`, enable tenant policies or supply real provider credentials for tests.
Missing PostgreSQL/browser/Docker prerequisites must be recorded as skips, never passes.

## Evidence and measurement boundaries

| Measurement | Method / denominator |
| --- | --- |
| Schema validity | Validated candidate batches / 12 mocked response cases (including intentional faults). |
| Normalized coordinates | Coordinates inside [0,1] / all 7 supplied click candidates, including the invalid one. |
| Safe rejection | Invalid JSON, refusal, out-of-bounds and HTTP 429 produce no candidates, one attempt each. |
| Locator conversion | Actual Playwright grounding for native button, link, div/span role=button and scrolled control; disabled targets stay unresolved. |
| Trace completeness | Actual operation before/after frames; separate from schema validity. Gemini v4 success checks 4 retained frames for navigation plus link click, with proposal/locator linkage. Legacy checks two retained state images. |
| Retry safety | Duplicate execution/unknown outcome, lease fencing and restore tests verify no repeated physical action. |

The expected response counters are 8/12 schema-valid, 6/7 normalized-coordinate
candidates and 4/4 safe rejections. These are intentional synthetic distributions,
not model quality or coverage estimates. A stop for a disabled control exercises
the output contract; disabled-target enforcement is separately tested in Playwright.
Sibling restoration, SQL visibility during model calls, authorized result reads,
draft-generation failure, approval and deterministic execution use existing durable
integration tests. `benchmark.vision.summarize_locator_trace` retains separate
locator/frame denominators; no production benchmark engine changes were needed.

Final validation on 2026-10-17:

- Offline Python harness: **560 passed, no skips**, 282.65 seconds. Three
  configured-stack Compose tests excluded (not passed). Eleven existing
  collection/deprecation warnings; owned UUID databases removed afterward.
- Worker grounding/operation suite: **32 passed, no skips**, 59.6 seconds.
- Final dashboard browser suite: **10 passed, no skips**, 14.4 seconds;
  dashboard unit suite: **31 passed, no skips**.
- Repository Ruff, dashboard/worker typecheck and dashboard production build passed.
  Existing Next workspace-root/ESLint-plugin and Node module-type warnings remain.
- Response counters measured by the passing manifest test: **8/12** valid batches,
  **6/7** in-range coordinate candidates, **4/4** safe rejections. Browser/SQL
  locator and trace invariants in the table above also passed; no combined
  model-quality or exhaustive-coverage score is inferred.

Exact commands, files and deviations are in the canonical
[plan record](../../../plan/17102026112826-gehihi-vision-provider/README.md).
The isolated PostgreSQL container and local dashboard process were stopped after
validation; no application stack service was restarted.

The 2026-10-17 implementation did not change prompt behavior or token guards.
Mocked output cannot establish that
the 1000-token response limit is sufficient for real reasoning/output. If a future
authorized canary truncates or exhausts quota, retain its safe failure and seek a
separate decision before changing limits/model. The stable model name is not an
immutable weights hash. Free-tier account availability and zero monetary cost
are not certified by these checks.

## Coordinate regression (2026-10-18)

Prompt v5 explicitly confines click/type coordinates to the current screenshot
and requests scrolling before addressing offscreen controls. Gemini candidate
batches now use a JSON schema derived from the shared action contract, including
coordinate ranges and the requested candidate cap. The manifest source hashes
were refreshed for this revision; the historical full-suite results above refer
to the previous revision. Token and traversal limits are unchanged.

A live, read-only adapter replay reproduced `invalid_candidate_schema` with
multiple click `y` values above 1, despite a complete JSON response. Replaying the
same authorized image after the fix produced 17 validated candidates (16 click,
1 scroll), 809 completion tokens, and a normal stop. No browser action was
dispatched during this diagnostic. Raw image, intent and provider content are
not included here. This verifies the corrected adapter response for that image,
not complete browser coverage or a full live-provider exploration canary.

Validation for this revision: repository Ruff passed; the isolated offline
harness passed 187 tests with no skips, covering the adapter, model batch,
executor, runtime, benchmark manifest, policy, submission and provider browser
integration suites. Browser integration uses mocked provider HTTP and checks
navigation followed by a verified click with four retained frames, plus safe
stops on invalid coordinates. One existing Starlette/httpx deprecation warning
remains. The diagnostic PostgreSQL container was removed after the tests.

## Dynamic viewport and capture regression (2026-10-18)

A real session stopped with `state_restore_failed` after setup and two rejected
restore/replay operations. Offscreen carousel mutations invalidated the whole-DOM
fingerprint while the model was thinking. The worker now fingerprints rendered
viewport semantics and geometry, retaining URL, scroll and page-wide form guards.
Checkpoint state is bound to a stable after capture, and navigation via a link
gets the same bounded destination-settle window as explicit navigation.

The isolated live-persistence suite passed 23 tests, including a continuously
animated offscreen fixture and two sibling clicks. Browser regression checks
cover moved controls, overlays, iframe content, hidden accessible labels,
offscreen form values, hydration during capture, failed restoration, missing
after images and slow destination hydration. TypeScript checks passed.

After rebuilding the Docker worker, an owned, temporary browser on the authorized
target kept its initial checkpoint valid after an 11-second model-delay simulation
and completed five operations: navigate, click Events, back, replay navigation,
click Guide. All five retained paired frames. This smoke uses predetermined
coordinates through normal worker grounding; it does not call Gemini, assert
complete button coverage, create an application session or change test verdicts.
Temporary browser artifacts and the isolated database container were removed.

## Partial-report and invalid-reply regression (2026-10-18)

Prompt v6 adds explicit normalization arithmetic and a decimal-place example for
controls near the top edge, plus short expected outcomes within the existing
response cap. No live-provider accuracy claim is made for this prompt revision.
Malformed responses no longer discard already validated sibling candidates;
no model retry occurs, and the final status remains partial/unavailable.
Every session result now includes an observation report independent of generated
drafts and deterministic execution reports, including historical stopped sessions.

Validation: 137 isolated Python checks passed across live persistence, report
routes/authorization, executor, benchmark manifest, model batch and Gemini adapter
suites. Twenty dashboard browser tests passed, including report discovery,
download links, interrupted-session findings and mobile layout. TypeScript,
Ruff and production dashboard build checks passed. Fixture providers remain mocked.
