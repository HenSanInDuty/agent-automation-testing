# Phase 5 — Thesis benchmark

**Status:** planned  
**Prerequisite:** Phase 4 complete  
**Exit:** controlled experiments produce repeatable, exported results for the
baseline, proposed system, and ablations.

## Checklist

- [ ] Create controlled Web UI targets and seeded data with pinned browser,
  runner image, test revision, and environment configuration.
- [ ] Define locator, DOM, text, timing, product, environment, and flaky fault
  scenarios with expected root causes.
- [ ] Create a versioned benchmark manifest: scenario, inputs, expected result,
  test revision, seed, and evidence references.
- [ ] Implement the deterministic Playwright baseline and record outcome,
  duration, artifacts, and reproducibility data.
- [ ] Run baseline, single-agent triage, multi-agent triage/healing proposal,
  and selected-evidence ablation conditions.
- [ ] Calculate precision/recall/F1, valid/false-healing rate, median
  triage/recovery time, overhead, token cost, and repeatability.
- [ ] Export anonymised data and scripts to reproduce every thesis chart/table.

## Completion demonstration

Given the same manifest and seed, a fresh environment reproduces an experiment
within declared tolerance.

## Validation

Manifest validation, repeated-run checks, result-schema tests, and reproducible
experiment scripts.
