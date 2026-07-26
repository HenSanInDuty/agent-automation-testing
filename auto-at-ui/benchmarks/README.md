# Controlled Web UI thesis benchmark

`manifest.v1.json` is the experiment source of truth. It pins the browser, worker image, test revision, seed and environment, and contains seven controlled fault scenarios. Evidence URIs use the `benchmark://` scheme so the exported result set includes no credentials, host paths, tokens or customer data.

Run it from the repository root:

```bash
uv run python scripts/run_benchmark.py
uv run python scripts/run_benchmark.py --output benchmarks/exports/results.v1.json
```

The harness is intentionally offline: it materialises the published, ground-truth observations for baseline and agent conditions. It does not call an LLM, alter a suite, or claim that a recorded comparison is a live agent evaluation. The `targets/web-ui` fixture is a local, seeded HTTP target for reproducing Playwright evidence collection; Docker Compose exposes it as `benchmark-target`.
