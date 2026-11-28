# Phase 12 — test report (QA r1)

QA VERDICT: PASS

Environment: Windows 11, `uv run`, `CODEX_BRIDGE_ENABLED=false`, `--basetemp` in scratchpad. Real PostgreSQL disposable fixture
(127.0.0.1:55437) was reachable, so 7 cases ran against a real DB and real `transactional_session` (none skipped). No shared Docker stack touched.

Output:
```
uv run ruff check .  -> All checks passed!
pytest tests/test_qa_p12_policy_audit.py ... (8 files incl. vision_agent_engine_selection, vision_policy_persistence)
  -> 155 passed, 5 warnings in 53.69s
pytest tests/test_qa_p12_policy_audit.py -> 13 passed
hgraph add vision-exploration tests/test_qa_p12_policy_audit.py -> Đã thêm 1 file (tổng 65)
hgraph check -> 8 graph, 546 file source / ✔ Không có vấn đề.
```
`hgraph check --changed` still lists tracked uncommitted files with the `auto-at-ui/` prefix (known false positive, see memory note;
`generation.py` is covered). Neither phase 12 test file is listed.

Files that call `/policy`: dashboard_route_contracts, generation_policy_audit, vision_agent_engine_selection, vision_policy_persistence,
vision_policy_routes, vision_tree_capacity — all run above.

Coverage: criteria 1-6 all verified (see test-cases.md). Criterion 6 graph: `generation.py` belongs to the graph, test files added.
Stress test: không cần — một ghi policy đơn lẻ mỗi request, không vòng lặp lớn, query hay lock mới.

Not tested: real Docker/live server end-to-end through the dashboard UI (not needed for a route-level audit); migrations not touched.
Note N1: PK of `project_execution_policies` is project_id only, cross-tenant PUT on an existing project id yields 500 (pre-existing, no data leak).
