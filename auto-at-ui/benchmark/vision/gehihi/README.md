# Gehihi synthetic evaluation

Provider `gemini`; model `gemini-3.8-flash`; prompt `vision-exploration-v4`;
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

No prompt behavior or token guards changed. Mocked output cannot establish that
the 1000-token response limit is sufficient for real reasoning/output. If a future
authorized canary truncates or exhausts quota, retain its safe failure and seek a
separate decision before changing limits/model. The stable model name is not an
immutable weights hash. Free-tier account availability and zero monetary cost
are not certified by these checks.
