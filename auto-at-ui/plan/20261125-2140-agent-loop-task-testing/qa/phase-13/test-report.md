# Phase 13 — test report (QA r1)

QA VERDICT: PASS

Environment: Windows 11, `uv run`, `CODEX_BRIDGE_ENABLED=false`, `--basetemp` in scratchpad. Disposable PostgreSQL fixture
(127.0.0.1:55437) reachable, so route tests ran on a real DB (none skipped). Shared Docker stack untouched.

## Output
```
uv run ruff check .                      -> All checks passed!
pytest tests/test_qa_p13_review_guards.py tests/test_agent_task_review_guards.py -> 52 passed (Q 24 + dev 28)
required 13-file group                   -> 157 passed, 14 warnings in 69.44s
wider grep(decide|revised-draft|evidence), chunk A (22 files) -> 467 passed, 3 skipped, 2 failed
wider chunk B (13 vision files incl. preflight)               -> 271 passed, 1 failed (stopped by -x at preflight)
hgraph add agent-task-draft tests/test_qa_p13_review_guards.py -> Đã thêm 1 file (tổng 27)
hgraph check -> 8 graph, 548 file source / Không có vấn đề.
```

## Failures that are not this phase
- `test_vision_target_preflight.py::test_changed_video_copy...[replacement]` (`invalid_step_deadline`): known, before phase 13.
- `test_qa_r8_agent_evidence.py::test_worker_dom_skips_private_inputs_and_redacts_sensitive_names`: known (vision-dom.ts phase 02).
- `test_codex_bridge_benchmark.py::test_offline_manifest_provenance_and_explicit_live_boundary`: NEW to the list, still not caused by
  phase 13 alone. `benchmark/vision/codex/manifest.json` pins sha256 of `api/v1/routes/generation.py` (= HEAD hash b79c7d4...) and
  `tests/test_vision_tree_capacity.py`; both were already edited by earlier uncommitted phases (phase 12 edited generation.py, and tree_capacity
  is unrelated to phase 13), so it failed before phase 13. Needs manifest regeneration at commit time. Leader should know.

## Coverage
Criteria 1-7 verified (see test-cases.md). Criterion 6: ADR section compared character for character with the PM draft plus the user's
edits (a) and (b); Amended line and the changed sentences checked.

## Observations (not failures)
- N1 (nit, fix before closing): `docs/graphs/agent-task-draft.md:107` still says `reporting_events.py` is "chưa truyền cờ: xem báo cáo phase 13". Since
  r2 the flag is wired. Docs-only, `hgraph check` does not catch prose.
- N2: local header auth defaults a missing `X-Actor-Id` to `local-developer` with role `tenant_admin` (pre-existing `_local_principal`). Same-person
  rule is therefore only as strong as the identity source; it holds for session accounts and explicit headers (TC-12).
- N3: the requester may reject their own agent draft if holding DECIDE_PROPOSAL (documented behaviour, TC-08).

## Not tested and why
- Wider-grep vision files that timed out twice at 400-530 s (handoff_repository, live_persistence, migration_compatibility, model_batch,
  operation_repository/transport, page_batch, results, screen, benchmark, replay, restoration, reload, vision_accuracy_*): not in the
  blast radius (`hgraph impact` of generation.py/reporting_events.py lists only test_reporting_event_processor, test_vision_locator_pipeline, both run).
  Ran out of time per command limit, not a known failure.
- Real Temporal/worker/Docker end-to-end and a real model call: phase 14 territory; the model is a fake in tests.
- Artifact content (trace/video) containing values: accepted by ADR, not tested.

Stress test: không cần — một request quyết định mỗi lần, không vòng lặp lớn, không query/lock mới.

## hgraph
`hgraph check --changed` lists tracked uncommitted files with the `auto-at-ui/` prefix (known false positive); the new test file is not listed
(it is in agent-task-draft). `hgraph check` (non-changed) is clean.
