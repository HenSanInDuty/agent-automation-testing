# Live Codex / Mongchiton — 2026-11-05

**Outcome: partial exploration, stopped with `bridge_stale_result`.**

- Target: `https://mongchiton.vn`.
- Session: `95c8129e-f321-4f4f-9c28-378c34806b83`.
- Dashboard: <http://localhost:3000/agent?vision=95c8129e-f321-4f4f-9c28-378c34806b83>.
- Provider/model: existing Codex account, `codex_cli` / `gpt-6-luna`.
- Method: authenticated local development API reload of the user's failed session
  `13210987-86bc-4328-8a8e-b7f7a0a4a32c`, preserving its saved task and target.
- Policy unchanged: 20 model-call limit, 10 hops, 50 states, 120 seconds per step.
- Existing page/text and optional screenshot consent were read and echoed through
  the API's input-policy fingerprint. All three actual jobs used DOM text; no image job.
- Path: deployed application, bridge, Temporal worker, Playwright and database.
  The offline target-scoped prototype was **not** integrated or exercised.

## Measurements

| Metric | Observed |
|---|---:|
| Session elapsed, queued to terminal activity | 121.036 s |
| Model jobs completed / submitted | 3 / 3 |
| Job round-trip times, including bridge queue/validation | 8.51 / 13.24 / 9.99 s |
| Input / output tokens reported | 16,762 / 544 |
| Browser operations completed | 16 |
| Completed exploration clicks | 4 |
| Browser operations failed / rejected / unknown | 0 / 0 / 0 |
| Retained frames | 32 |
| Distinct controls recorded / completed | 35 / 4 |
| Inventory completeness | Limited |
| Deterministic test execution | Not started |

Token metadata is not a billing estimate. Recorded controls are not a denominator
for whole-site coverage. The application reports `coverage=not_established` and
`business_outcome=unverified`.

## Failure evidence

The third model job reached `codex.completed` at **15:20:01.459750 UTC**. The session
then reached `unavailable / bridge_stale_result` at **15:20:01.735175 UTC**, with no
further browser action. The provider exchange completed; the result was rejected
at the subsequent application state-validation stage.

This is consistent with the post-response `check_state()` guard in
`apps/control-plane/application/codex_candidates.py`: a proposal is discarded if
the checkpoint no longer matches after the exchange. The retained diagnostics do
not identify the exact DOM element or state component that changed.

Unlike the earlier offline reservation reproduction, this attempt **did dispatch
the third request and receive a response**. Fixing reservation accounting alone
does not cover this observed failure. Fresh observation / target validation after
model latency must be tested in the actual orchestration path.

No retry was submitted after this terminal result. No draft was approved, no test
run was manually dispatched, and no provider policy or deployed application code
was changed. One live trial is not an availability or stability estimate.

Raw metadata, activity timestamps, operation ledger, token usage and deployed image
IDs: [live-mongchiton-20261105.json](live-mongchiton-20261105.json).

Subsequent read-only diagnostics isolated character-carousel autoplay as a
reproducible source of checkpoint drift at the relevant viewport; see
[the diagnosis and counterfactual](STALE-RESULT-DIAGNOSIS-20261105.md).
