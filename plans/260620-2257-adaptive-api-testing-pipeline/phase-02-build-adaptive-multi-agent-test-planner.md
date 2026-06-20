---
phase: 2
title: "Build adaptive multi-agent test planner"
status: pending
priority: P1
dependencies: [1]
---

# Phase 2: Build adaptive multi-agent test planner

## Overview

Generate a reliable rule-based baseline, choose 1-5 specialized planners from deterministic complexity, then debate and consolidate their proposed cases.

## Requirements

- Complexity decision is deterministic, explainable, bounded to 1-5 agents, and persisted.
- Planner roles cover positive, negative/schema, auth/security, boundary/data, and resilience/idempotency concerns.
- Every case maps to one or more source obligations; invented behavior is labeled as an assumption.
- Consolidation removes semantic duplicates without losing traceability.

## Architecture

Create an `AdaptiveApiTestPlannerCrew` using existing `AgentFactory` configurations. Complexity uses endpoint count, parameters/fields, responses, auth/headers, validation rules, and state-changing methods. Map score bands to agent count and select roles in fixed priority order. Run candidates concurrently where safe, then one critique round and deterministic merge/deduplication.

## Related Code Files

- Create: `D:/CV/auto-at/backend/app/crews/adaptive_api_test_planner_crew.py` - bounded orchestration facade.
- Create: `D:/CV/auto-at/backend/app/services/api_test_planning/complexity.py` - score and role selection.
- Create: `D:/CV/auto-at/backend/app/services/api_test_planning/consolidator.py` - normalization, traceability, deduplication.
- Modify: `D:/CV/auto-at/backend/app/schemas/pipeline_io.py` - complexity, obligation, candidate, and plan schemas.
- Modify: `D:/CV/auto-at/backend/app/db/seed.py` - five planner configs, adaptive node, template version bump.
- Create/modify: targeted upgrader under `D:/CV/auto-at/backend/app/db/` - upgrade only an unchanged shipped v4 template; flag customized templates.
- Modify: `D:/CV/auto-at/backend/app/core/dag_pipeline_runner.py` - minimal built-in dispatch entry.
- Create/modify tests under `D:/CV/auto-at/backend/tests/` for complexity, concurrency, debate, deduplication, schemas, and migration.

## Implementation Steps

1. Extract normalized obligations: success/error responses, required headers/auth, fields/rules, parameters, and response assertions.
2. Keep `generate_test_cases()` as baseline; attach obligation IDs and source evidence.
3. Implement stable complexity weights and role selection. Cap selected agents and concurrent LLM calls at five.
4. Seed distinct planner prompts with strict JSON/Pydantic output and no secret echoing.
5. Execute selected agents with isolated context; retain successful proposals when one agent fails.
6. Give each agent a compact anonymized summary of other proposals for one critique/debate round.
7. Consolidate baseline + proposals by endpoint/method/input mutation/expected outcome fingerprint; keep provenance/conflicts.
8. Replace the shipped generator node through a version/fingerprint-guarded migration; never overwrite a customized DAG silently.

## Success Criteria

- [ ] Same document/config always selects the same count and roles.
- [ ] Simple fixture selects one agent; complex fixture selects five.
- [ ] At least one critique round occurs when two or more agents run.
- [ ] Invalid agent JSON is rejected or quarantined.
- [ ] Final plan has unique IDs, obligation links, provenance, assumptions, and executable request data.
- [ ] Agent failure still yields baseline cases and a visible warning.
- [ ] Fresh and safely upgradable installs receive the template; customized templates remain untouched with an actionable warning.

## Risk Assessment

Main risks: LLM latency/cost, nondeterministic duplicates, prompt leakage, and silent template drift. Bound fan-out/debate, use typed outputs, redact secrets, keep deterministic fingerprints, and guard migration by version plus known-template fingerprint.
