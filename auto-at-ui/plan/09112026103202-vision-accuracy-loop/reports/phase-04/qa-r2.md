STATUS: PASS

# QA r2 (round r8) - phase 04, ADR-040 flags A1/A2/A3

QA VERDICT: PASS
GRAPH: `hgraph check` clean (6 graph, 459 file). `hgraph check --changed` exit 1 with only `uncovered-changed` entries that carry the `auto-at-ui/` git-root prefix (known tooling issue, r7; `hgraph which` shows those files are in graphs). My own new test file drifted and was added with `hgraph add vision-agent-loop tests/test_qa_r8_agent_evidence.py`; no drift left.
Đã test: 49 QA cases (+ 159 focused, 463 agent-loop/config/results regression with 149 DB skips, 37 worker specs) - pass all / fail 0.
FAIL: none.
Observations: O1 `benchmark/vision/accuracy/evidence.py` `derive_detection` reports `inventory_complete=true` for an oracle-page state whose control rows are all junk (no credit, recall stays 0); O2 stored `page_inventory.page_url` may contain a query string (pre-existing); O3 old worker + flag on fails closed with `VisualWorkerUnavailable` (rebuild worker first).

Real output
```
uv run ruff check .                -> All checks passed!
pytest tests/test_qa_r8_agent_evidence.py -> 49 passed
pytest qa_r8 + dev r8 + accuracy binding/loop/metrics + worker contracts -> 159 passed
pytest agent loop/safety/engine/contracts/config/results -> 463 passed, 149 skipped (PostgreSQL 55437 unavailable)
tsc --noEmit -> exit 0
playwright vision-agent-evidence + vision-agent-mode --workers=1 -> 37 passed (3.4m)
r6 replay (--sources none/all/...) -> C 5/47, A 5/12, R 0/47, inventory incomplete, passed=false == stored r7 score
oracle hash 9242b33d... ; git diff HEAD metrics.py + oracle JSON -> empty
```
Chưa test được: live worker negotiation, dom_path on real carousel, real inventory size, model behaviour; DB-gated tests (skipped); `/result` and `/trace` HTTP with flags on end to end; dashboard with A3 data; worker regression specs beyond the two run (developer reported 111+123 green).
Stress test: không cần - no new large loop/query/lock; cap 100 controls covered by dev test.
Tài liệu: `qa/phase-04/r8-test-cases.md`, `qa/phase-04/r8-test-report.md`; automation `tests/test_qa_r8_agent_evidence.py` (new, QA) plus dev files. Product code untouched; test-only additions (also `docs/graphs/vision-agent-loop.md` got my test file added by `hgraph add`).
Processes: none left running (no docker/server; playwright runs finished).
