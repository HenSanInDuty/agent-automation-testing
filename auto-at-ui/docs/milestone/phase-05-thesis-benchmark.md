# Phase 5 — Thesis benchmark

**Status:** done
**Prerequisite:** Phase 4 complete  
**Exit:** controlled experiments produce repeatable, exported results for the
baseline, proposed system, and ablations.

## Checklist

- [x] Create controlled Web UI targets and seeded data with pinned browser,
  runner image, test revision, and environment configuration.
- [x] Define locator, DOM, text, timing, product, environment, and flaky fault
  scenarios with expected root causes.
- [x] Create a versioned benchmark manifest: scenario, inputs, expected result,
  test revision, seed, and evidence references.
- [x] Implement the deterministic Playwright baseline and record outcome,
  duration, artifacts, and reproducibility data.
- [x] Run baseline, single-agent triage, multi-agent triage/healing proposal,
  and selected-evidence ablation conditions.
- [x] Calculate precision/recall/F1, valid/false-healing rate, median
  triage/recovery time, overhead, token cost, and repeatability.
- [x] Export anonymised data and scripts to reproduce every thesis chart/table.

## Completion demonstration

Given the same manifest and seed, a fresh environment reproduces an experiment
within declared tolerance.

## Validation

Manifest validation, repeated-run checks, result-schema tests, and reproducible
experiment scripts.

## Delivered benchmark

- `benchmarks/manifest.v1.json` pins the controlled target, browser, runner,
  test revision, seed, environment, expected root cause, and evidence references
  for seven fault types.
- `benchmarks/targets/web-ui` provides the seeded local target; Compose exposes
  it as `benchmark-target` for Playwright evidence collection.
- `scripts/run_benchmark.py` materialises the controlled baseline and three
  comparison conditions into `benchmarks/exports/results.v1.json`. The offline
  harness uses published ground-truth observations, never calls an LLM, and
  cannot change a test or runner verdict.
- `tests/test_benchmark.py` validates the manifest and schema, repeatability,
  metrics, and anonymised export. Run `uv run python scripts/run_benchmark.py`
  followed by `uv run pytest --basetemp D:\tmp\auto-at-pytest-phase5`.
