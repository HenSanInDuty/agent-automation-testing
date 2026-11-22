# Exploration stability experiment

This offline experiment follows investigation of session
`13210987-86bc-4328-8a8e-b7f7a0a4a32c` (`bridge_stale_result`). It does not replay
that website, call a provider, change tenant policy, or replace the application runner.

## Questions and measurements

1. Can the current candidate service consume a reservation without sending a model
   request, preventing the orchestrator's zero-call refresh gate from opening?
2. In a controlled browser, does checking the selected target and its context
   allow progress when an unrelated control changes, while still blocking the
   specified dangerous changes?
3. Do the existing real PostgreSQL/browser regression tests still pass?

These are separate measurements. Passing an expected-failure regression test is
not a successful exploration. Completing a synthetic task does not establish
real-provider availability or general website coverage.

## Protocol

- Reservation experiment: actual `CodexCandidateService`, existing synthetic
  exchange fixture, four schedules, 20 repetitions each. Compare actual exchange
  invocations with reported calls and the zero-call refresh eligibility condition.
- Browser experiment: real Chromium, 1280x720 viewport, a new isolated browser
  context for each trial. Twelve scenarios, two policies, 20 repetitions each
  (480 trials). Alternate policy order every repetition.
- Both browser policies perform up to three sequential actions, reacquire state
  before each action, use the same exact-name role locators, retain the original
  node identity, and use the same Playwright actionability checks and timeouts.
- The checkpoint policy calls the production `inspectState` / `equivalentState`
  functions with the default `all` interaction scope. It is a reduced
  checkpoint-gate baseline, **not the full BFS runner**.
- The experimental policy permits unrelated control changes and target movement,
  but preserves URL/form context, exact node identity, semantic identity and
  locator uniqueness. This is a **benchmark-only prototype**, not an integrated
  replacement for persistence, leases, policy checks, or worker dispatch.
- A scripted planner contributes 10 ms per action. No generated prompt, model,
  quota, external target, credential, or screenshot transfer is involved.
- Mutations are injected between observation and validation. Lost acknowledgement
  is simulated after one confirmed physical click; both policies must stop without
  clicking again. A popup trial must observe and close its synthetic popup before
  continuing on the parent page.

Expected completion: stable page, passive text update, unrelated link update,
target movement, popup. Expected safe block: target rename/replacement/occlusion,
duplicate locator, changed form context, changed URL. Expected unknown stop:
lost acknowledgement after the first click. Each expected outcome is determined
independently from the observed click ledger, not from the strategy's status alone.

Report task completion, correct safe stops, forbidden/duplicate clicks, planner
invocations and p50/p95 wall time separately. Repeating deterministic cases checks
repeatability; the repetitions are not independent samples of production uptime.
Timing includes page setup and browser operations, excludes browser/context launch,
and may be affected by concurrent regression testing. It is not model latency.

## Reproduce

From the repository root, with Docker Desktop running Linux containers:

```powershell
uv run --no-sync python benchmark/vision/sequential/run.py
uv run --no-sync python benchmark/vision/codex/run_offline.py -q --tb=short tests/test_codex_candidate_service.py tests/test_vision_page_batch.py tests/test_vision_live_persistence.py
```

The existing pinned offline image contains Python dependencies, Playwright 1.50.1
and Chromium, with no Codex executable or `.env`. Benchmark execution uses
`--network none`, no host mounts and no application services. Regression execution
uses its own disposable PostgreSQL instance in an isolated network namespace.
Image building may download dependencies; test execution cannot contact providers.

Raw benchmark rows and source hashes are in `results-20261105.json`. The regression
runner prints the location of its JSON summary under `.pytest-artifacts/`.
`REPORT.md` records the measured results and limitations after the run.

## Scope of a positive result

Zero unsafe clicks in these fixtures is a necessary gate, not a safety proof.
Further integration work must cover the observation/dispatch race, asynchronous
navigation and popup attribution, worker loss, tenant/consent revocation, durable
operation identity, retries, and retaining partial evidence. A real-model canary
and the user's target remain separate validation steps. Neither a production
rollout nor a real inference request is performed by this experiment.

## Separately authorized live run

Continuation status, deterministic viewport implementation and live results:
[RESUME-20261108.md](RESUME-20261108.md).

Further capture/heartbeat stability work:
[STABILITY-20261108.md](STABILITY-20261108.md).

Latest continuation, popup return-state fix and validation:
[COMPLETION-20261109.md](COMPLETION-20261109.md).

After the offline comparison, the user explicitly requested real Codex against
Mongchiton. The deployed application's single live trial is documented separately
in [LIVE-MONGCHITON-20261105.md](LIVE-MONGCHITON-20261105.md), with raw metadata in
`live-mongchiton-20261105.json`. These live results are not mixed into the synthetic
A/B completion counts, and they do not exercise the benchmark-only prototype.
