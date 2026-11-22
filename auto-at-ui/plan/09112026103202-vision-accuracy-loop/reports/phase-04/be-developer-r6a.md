STATUS: DONE (harness change implemented and verified offline; decision needed from user on evidence for the remaining gates, see ESCALATE)

# be-developer r6a - credit agent_loop clicks in the accuracy harness (direction A)

CONTEXT_CHECK
- conventions: docs/code-standards.md (index) -> AGENTS.md read verbatim (uv, tests with each behavior change, ruff + pytest baseline, round handoff rules). No docs/api-conventions.md exists in this repo (not needed: no API change).
- graphs: no graph covered `benchmark/vision/accuracy/*` at brief time; read docs/graphs/vision-agent-loop.md (only a one-line note about `evidence.py`) and vision-exploration.md. Created new graph `vision-accuracy-harness` (see GRAPH_UPDATE).
- blast radius: hgraph reported 0 dependents / 0 dependencies for the three files (they load each other by sys.path/importlib, which hgraph does not see). Real dependents found by grep: tests/test_vision_accuracy_loop.py, tests/test_vision_accuracy_metrics.py, tests/test_vision_agent_loop.py:1031 (loads evidence.py `export_operation`), tests/test_vision_agent_safety.py:20 (reads the oracle), scripts none. All run green.

## Impact inventory

Database: không đụng. No table, column, migration, backfill, index, lock. Read-only SELECTs on the local Postgres were used to survey (states/checkpoints/steps of the r6 session); nothing written.

Files
- `benchmark/vision/accuracy/evidence.py` (edit): `export_grounding`, `normalize_label`, `box_iou`, `binding_error`, constants. `export_locator`/`export_operation` output unchanged (only the status set became a constant).
- `benchmark/vision/accuracy/run.py` (edit): `Loop.trace` (paging extracted from `collect`, same checks), `Loop.ground`, `grounding_document`, `check_grounding`, `evaluate` uses `binding_error`, new `ground` CLI command. `collect` also writes `grounding.json`.
- `tests/test_vision_accuracy_binding.py` (new, 21 tests): needs a multi-operation fake trace; the existing `FakeAPI` is single-operation.
- `benchmark/vision/accuracy/README.md` (edit): section "Binding agent_loop (role) locators".
- `benchmark/vision/accuracy/AGENT-LOOP-01-20261120.md` (append only): "Round r6a" section; r6 text not edited.
- `docs/adr/039-agent-loop-role-binding-in-accuracy-harness.md` (new). `docs/adr/038-vision-agent-loop-engine.md` already exists, so the next free number is 039.
- `docs/graphs/vision-accuracy-harness.md` (new graph).
- `benchmark/vision/accuracy/runs/1c56623e.../grounding.json` and `rescore-role-binding.json` (new files in the r6 run folder; `evidence.json`, `assessments.json`, `detection.json`, `score.json` untouched, `cmp` identical).
- Not touched: oracle JSON (git diff exit 0, hash `9242b33d5e4cdd155b6642262c32f166b365edeec7d7b9642c5b88df35147a4e` re-computed), `metrics.py` (git diff exit 0), apps/**, workers/**, packages/contracts/**, plan README, any direction-B file.
Callers of changed signatures: `export_locator`/`export_operation`/`Loop.collect|evaluate` signatures unchanged. `binding_error` and `export_grounding` are new. Public contract touched: harness artifact `grounding.json` (`vision-accuracy-grounding-v1`) and CLI command `ground`; no API/event/env/config change.
Existing tests: tests/test_vision_accuracy_loop.py (collect/evaluate happy path with dom_path, still passes unchanged), metrics tests. Gap before: no test for role locators at all.

## Ladder (new helpers)
- Rung "do nothing / manual only": rejected, it leaves the benchmark unable to score the engine.
- Rung "change oracle / loosen rule / change contract": forbidden or out of scope.
- Rung "reuse existing function": `export_locator` cannot carry role/name/box without changing the `evidence.json` schema (would change retained-run semantics) -> a sidecar `grounding.json` instead. Kept in the existing `evidence.py` and `run.py`; no new module.
- New code is small, pure and table-tested: one binding function, one export function, two tiny helpers (label normalization, IoU). One new test file only because the existing fake cannot express multiple operations.

## Design (what was found, not assumed)
- Evidence available through the public API only: trace `locators[].descriptor` (strategy `role`, accessible name, role), `bounding_box` (normalized to the viewport), operation `executed_click` (click point and `viewport_width/height`), `before_page_id/after_page_id` (tab identity). The exporter used to drop all of that.
- Not available through the public API: page URL/fingerprint and scroll offset of the click (they exist only in `visual_exploration_states.checkpoint` in the DB), a DOM snapshot, any page inventory (`page_inventory` NULL in all 23 r6 states; `/result` `pages=[]`; step log keeps refs like "1:2" only; `observe_dom` output is rendered into the prompt and discarded). So detection/inventory cannot be rebuilt independently inside the harness: reported incomplete.
- Binding rule for a path-less `role` locator (ADR-039): root tab, oracle viewport, same role (`a` link, `button` button), normalized name (accent/case/space, non-empty) equality, box IoU >= 0.8, exactly one oracle candidate and it equals the reviewer's `target_id`, click point inside the oracle box, one credit per target. Path locators keep the old equality rule, untouched.

## Red -> green
Red (new test `test_r6_shape_five_header_clicks_bind_to_oracle_and_score_matches_manual_review` against the old `run.py`, 5 header clicks + 3 tab buttons + 4 rejected, real r6 boxes/click points, real oracle):
```
benchmark\vision\accuracy\run.py:287: ValueError
E   ValueError: assessment binding does not match oracle
1 failed, 20 deselected
```
Green (after the change): same test passes: C 5/47, A 5/12, covered `mct-01,02,04,05,06`, recall 0/47, inventory incomplete, passed false.
Negative tests (all must raise `assessment binding does not match oracle (<reason>)`): label differs; box off by 20 px; link vs button; oracle button but locator link; popup tab (`off_root_page`); other viewport; click outside box; button not in oracle; two candidates (`ambiguous_oracle_match`); empty name; reviewer names another target (`target_mismatch`); locator not verified; non-role strategy without grounding; target credited twice (`already credited`). Plus: tampered or stale grounding (`grounding does not match evidence`), grounding export allowlist (no extra keys leak, out-of-range box -> None), unverified attempts still count in accuracy, normalized label + duplicate labels disambiguated by box (positive controls).
Old runs: `test_old_runs_keep_their_credited_bindings_and_stored_scores` walks every retained run folder with `score.json` and matching oracle hash, asserts every credited assessment still passes the unchanged path rule and that `metrics.score` reproduces the stored `score.json` exactly (runs and credited counts asserted non-zero).

## Verification (real output)
```
uv run ruff check .                     -> All checks passed!
uv run pytest tests/test_vision_accuracy_binding.py tests/test_vision_accuracy_loop.py tests/test_vision_accuracy_metrics.py
                                         -> 57 passed in 1.98s
CODEX_BRIDGE_ENABLED=false uv run pytest tests/test_vision_agent_loop.py tests/test_vision_agent_safety.py
                                         -> 73 passed, 38 skipped, 1 warning in 82.22s
git diff --exit-code -- benchmark/vision/accuracy/oracle-mongchiton-1280-v1.json benchmark/vision/accuracy/metrics.py -> exit 0
hgraph check                            -> ✔ Không có vấn đề. (exit 0)
```
(pytest needed `--basetemp` under the scratchpad because `C:\Users\hen\AppData\Local\Temp\pytest-of-hen` denies access in this sandbox.)

## Re-evaluation of r6 (iteration 1c56623e-8f37-4705-946b-5f1a6752f81c, offline copy, GET only)
Method: stored trace re-read with `Loop.ground` (read-only GET, trace revision equals the stored evidence revision), evaluated in a scratch copy with the 5 existing content-addressed reviews; old artifacts not overwritten. Output: `runs/1c56623e.../rescore-role-binding.json`.
- Harness-derived binding with no reviewer input (8 role locators): seq 2 SU KIEN -> mct-02, 6 DIEU KHOAN -> mct-04, 9 CONG DONG -> mct-05, 11 HO TRO -> mct-06, 14 TRANG CHU -> mct-01; seq 3 "Tin Tuc", 4 "Su Kien", 5 "Cam Nang" (tab buttons) -> no candidate. Identical to the manual review (5 of 5; 3 decoys with equal labels rejected).
- Raw counts under the new rule: C 5/47 (10.64%), A 5/12 (41.67%), detection R 0/47, P 0/0 (n/a), inventory_complete=false, unsafe 0, unsettled 0, passed=false. Same as the manual ceiling; the change did not raise anything above what was independently reviewed.
- Ceiling of the evidence as exported (raw counts, not a claim of achievement): 47 positives; 16 inside the first 1280x720 viewport and bindable; 31 below the fold (no scroll offset exported); 15 positives (mct-21, 29, 32, 44-47, 51-58) are unnamed or `div` so role+name can never bind them => at most 32/47 (68.09%) even with scroll evidence. C > 95% needs 45/47.

## Anti-gaming
- Old measurement unchanged: the path rule is the only rule for any locator with a path; role binding is reachable only when `path is null`, which was an unconditional failure before. The old-run test proves identical bindings and identical stored scores for every retained run.
- No threshold, oracle, metric definition, review or frame requirement changed. Role binding is an additional necessary gate on top of the content-addressed outcome review, frame checksums and `metrics.score`.
- Stricter than the path rule on purpose: unique candidate, viewport, click-in-box, root tab, one credit per target. Unbindable cases (below fold, unnamed, other tags, popups) earn nothing and still count as attempts in accuracy.
- Detection is never inferred from credited clicks (that would give P = 100% from a tiny denominator).
- ADR-039 written; no "ceiling" claim without counts (above).

## Remaining risks
1. Page identity of a click is not exported: a header link clicked on another page of the same site (r6 seq 14 TRANG CHU was clicked on /cam-nang) binds like the homepage one. The outcome review (before/after frames, declared destination) decides the outcome, and the old path rule has the same property for same-structure headers. Mechanical page identity needs the page URL fingerprint in the trace.
2. Box comparison assumes scroll offset 0 (viewport box == oracle document box). Fixed headers match at any scroll; in-flow elements at scroll > 0 simply fail to match (under-credit, never over-credit), except the contrived case of duplicate-labelled controls displaced onto each other's position.
3. Reviewer assessments are still manual inputs (the 5 outcome reviews of r6); the harness only verifies binding and frames.
4. `hgraph check --changed` exits 1 for tooling reasons unrelated to this work (see GRAPH_UPDATE).

## ESCALATE / NEEDS_USER_INPUT
ESCALATE
- vấn đề: agent_loop cannot reach C > 95% or inventory-complete detection with the evidence the control plane exports today, whatever the harness does. Raw counts: 47 positives; 16 bindable (first viewport, named); 31 below the fold; 15 unnamed or `div`; detection inventory not persisted (23/23 states `page_inventory` NULL, `pages=[]`).
- cần quyết định của user (each is a control-plane/worker/contract change, not done here):
  1. Export per operation the checkpoint `scroll_x/scroll_y` and `url_fingerprint` in `/trace` (data already in `visual_exploration_states.checkpoint`; no migration). Cost: roughly 0.5 to 1 day (trace serializer + contract field + tests + harness 10 lines). Unlocks 32/47 and page identity.
  2. For the 15 unnamed/`div` targets: make agent mode ground anonymous controls with `dom_path` (worker `vision-dom.ts` does this only for visual-button scope) so the unchanged path rule applies; or approve a box+tag-only binding with higher IoU (this loosens identification: user decision, not made here). Cost of the first: 1 to 2 days worker + tests.
  3. Detection/inventory: persist each observation inventory (role, name, box, viewport, scroll) in the result `pages` (migration-free if stored in `page_inventory`, 1 to 2 days), or explicitly accept the engine-independent read-only audit (`audit-1280-*`, `baseline-20261109.json`) as the detection source for agent_loop (definition change, user decision).
- Until then every agent_loop run stays `inventory_complete=false` and `passed=false`; harness stays honest about it.

## GRAPH_UPDATE
- graph đã cập nhật: created `vision-accuracy-harness` (hgraph new + add + sync --apply; sections filled by hand).
- file mới đã đưa vào graph: benchmark/vision/accuracy/run.py (entry), evidence.py, metrics.py, tests/test_vision_accuracy_binding.py, tests/test_vision_accuracy_loop.py, tests/test_vision_accuracy_metrics.py. (`hgraph sync` notes the 4 non-entry files are not import-reachable because they are loaded via importlib/sys.path; they stay listed on purpose.)
- hgraph check: `✔ Không có vấn đề.` exit 0.
- hgraph check --changed: exit 1. It lists 53 changed files as `uncovered-changed`, including files already in graphs such as apps/control-plane/agents/vision/codex_service.py; `hgraph which` for my files says `vision-accuracy-harness`. Cause: the git root is `agent-at/` while the hgraph root is `auto-at-ui/`, so changed paths arrive with an `auto-at-ui/` prefix and never match. Tooling issue, not a graph gap. Output excerpt: `✖ [uncovered-changed] ... auto-at-ui/benchmark/vision/accuracy/evidence.py`.

## Handoff notes for the coordinator (paste into README, <= 10 lines)
- r6a (direction A, offline, harness only): `evidence.py`/`run.py` now bind path-less `role` locators to the oracle (root tab, oracle viewport, role, normalized name, IoU>=0.8, unique candidate, click in box, one credit per target); path rule untouched. ADR-039.
- r6 re-evaluated from stored trace: harness derived mct-01,02,04,05,06 by itself (3 tab-button decoys rejected) = manual review. C 5/47, A 5/12, R 0/47, P n/a, inventory incomplete, passed=false. No score raised above the manual ceiling.
- New: `run.py ground --iteration <id>` (adds `grounding.json` to earlier-collected evidence); `collect` now writes it. Artifacts: `runs/1c56623e.../grounding.json`, `rescore-role-binding.json`.
- Evidence ceiling today: 16/47 bindable (first viewport), 15 unnamed/div never bindable by role+name, no inventory. C>95% for agent_loop needs a user decision on exporting scroll/URL, dom_path for unnamed controls, and an inventory (see ESCALATE).
- Checks: ruff clean; accuracy tests 57 passed; agent_loop/safety tests 73 passed 38 skipped; oracle/metrics diff exit 0; `hgraph check` exit 0 (`--changed` exit 1 is a root-prefix tooling issue).
- Files: benchmark/vision/accuracy/{evidence.py,run.py,README.md,AGENT-LOOP-01-20261120.md}, tests/test_vision_accuracy_binding.py, docs/adr/039-*.md, docs/graphs/vision-accuracy-harness.md.
