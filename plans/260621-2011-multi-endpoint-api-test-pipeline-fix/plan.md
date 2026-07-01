---
title: "Multi-endpoint API test pipeline fix"
description: "Fix parser single-endpoint truncation + runner Base URL bullet regex so a 9-endpoint spec yields full coverage and runs."
status: complete
priority: P1
effort: 9h
branch: develop
tags: [backend, bugfix, parser, pipeline, coverage]
created: 2026-06-21
---

# Multi-endpoint API test pipeline fix

## Problem

A 9-endpoint MD spec (`TodoCode/api_documentation-pipeline.md`) yields only 2 test cases
(both `GET /api/tasks`), both SKIPPED, and the reporter claims 100% coverage. Two verified
root causes:

- **Bug 1 — Parser keeps only the first endpoint.** `_extract_sections` (`md_api_spec_validator.py:342-346`)
  records only the first occurrence per canonical section. `ParsedSpec` is a single-endpoint
  model, so 8 of 9 endpoints are dropped. Coverage is computed against the 1 surviving endpoint's
  obligations → false 100%.
- **Bug 2 — Runner Base URL regex rejects bullet `- `.** `api_test_runner.py:35` `_RE_BASE_URL`
  lacks `[-*]?`, so `- Base URL: http://localhost:8080` does not match → `base_url=""` → every
  executable case is skipped. Runner never receives the already-correctly-parsed `parsed.base_url`.

## Strategy

Make `ParsedSpec` multi-endpoint (`endpoints: list[ParsedEndpointSpec]`), keep backward-compat
properties (`.endpoint`/`.request`/`.responses` → first endpoint) so existing tests and the
`md_spec_verifier_crew` preview keep working, then loop over all endpoints in the generator and
obligation extractor. Fix the runner to consume the parsed `base_url` (primary fix) plus harden
its regex with `[-*]?` (defense-in-depth).

Data contract: `md_spec_parsed` is the serialized `ParsedSpec.model_dump()` produced by
`md_api_spec_verifier` and carried forward (NOT in `_NON_PROPAGATING_KEYS`,
`dag_pipeline_runner.py:46`) to every downstream node, including `api_test_runner`. Changing the
shape of `ParsedSpec` changes this inter-node contract — every consumer must validate the new shape.

## Phases

| # | Phase | Status | Effort | Depends on |
|---|-------|--------|--------|-----------|
| 01 | [Multi-endpoint ParsedSpec schema + parser](phase-01-parsed-spec-multi-endpoint-schema-and-parser.md) | ✅ complete | 3h | — |
| 02 | [Generator + obligations loop over all endpoints](phase-02-generator-and-obligations-multi-endpoint-loop.md) | ✅ complete | 2h | 01 |
| 03 | [Complexity, prompts & crew preview consumers](phase-03-complexity-prompts-and-crew-consumers.md) | ✅ complete | 1.5h | 01 |
| 04 | [Runner Base URL fix (parsed source + regex)](phase-04-runner-base-url-fix.md) | ✅ complete | 1h | 01 |
| 05 | [Tests + docs](phase-05-tests-and-docs.md) | ✅ complete | 1.5h | 01-04 |

> **Note:** the sample doc has **8** endpoints (not 9 as first estimated); the fix and tests assert
> the actual count. Code review: APPROVE (1 Medium + 3 Low, all non-blocking) — see
> `reports/code-reviewer-260621-2035-multi-endpoint-pipeline-fix-review-report.md`.

## Key dependencies

- Phase 01 is the blocker for 02/03/04 — it defines the new `ParsedSpec` shape + backward-compat
  surface. 02, 03, 04 can run in parallel after 01 (distinct file ownership — see each phase).
- Phase 05 validates the end-to-end behaviour and must run last.

## File ownership (no overlap across parallel phases)

- P01: `md_api_spec_validator.py`
- P02: `api_test_case_generator.py`, `consolidator.py`
- P03: `complexity.py`, `planner_prompts.py`, `api_test_case_crew.py`, `md_spec_verifier_crew.py`, `adaptive_api_test_planner_crew.py`
- P04: `api_test_runner.py`, `api_test_runner_crew.py`
- P05: `backend/tests/*`, `docs/*`

## Success criteria (whole plan)

- Parsing `TodoCode/api_documentation-pipeline.md` yields 9 endpoints.
- Generator emits multiple test cases spanning all 9 endpoints (not just `GET /api/tasks`).
- Coverage reflects obligations from all endpoints (no false 100%).
- A spec with `- Base URL: …` (bullet) does NOT skip executable cases.
- All existing tests in `backend/tests` still pass.
