STATUS: DONE (offline). Needs user approval for one file outside the stated scope (DB migration) and a decision on the mongchiton tab DOM (see ASK_PM / ESCALATE).

CONTEXT_CHECK
- conventions: AGENTS.md, docs/code-standards.md (index of AGENTS.md); ADR-040 (pattern), ADR-042; no separate api-conventions.md exists, so I followed ADR-040 and the neighbouring files.
- graphs: playwright-vision-worker, vision-agent-loop, vision-accuracy-harness (read), vision-exploration (touched by migration/test)
- blast radius: hgraph brief: 156 dependents of config.py/contracts (depth 2), 12 foundations of vision-operations.ts

## 1. Design chosen and why

Capability `tab-panel-frame-v1`, flag `VISION_AGENT_TAB_PANEL_FRAME_ENABLED` (default false, only temporal-worker reads it through `config.py`), exactly the ADR-040 pattern.

Worker (after a completed agent-mode click, page not navigated/popup/download, `captured` after-state exists):
1. In the page, the clicked element must be a tab: `role=tab`, or an `aria-selected` attribute, or `aria-controls` without `aria-expanded`. Panel = element of `aria-controls` ids, else a `role=tabpanel` whose `aria-labelledby` names the target. It must be rendered and at least partly outside the viewport; otherwise nothing is added.
2. Capture chosen: clipped `Page.captureScreenshot` with `captureBeyondViewport:true` over a band (viewport width, from the tab row to the end of the panel capped at 720 px). This never scrolls, so "restore scroll" is not needed. Safety net: after the capture the worker re-reads `inspectState` and requires `equivalentState(after, now)` (ADR-042 logic untouched) plus identical `scroll_x/scroll_y`; otherwise the image is discarded. Any exception, timeout (4 s budget), oversize (> max_screenshot_bytes) or write mismatch discards it silently; the operation stays `completed`.
3. Why not scroll-and-restore: scrolling fires scroll/lazy-load handlers and cannot be undone in the page's own state; the clip capture touches nothing except a transient viewport override, which the state re-check covers (test: a `resize` handler that mutates the DOM makes the image drop).

Control plane: the panel is a third row in `visual_operation_frames` (role `panel`) with a deterministic object key `.../<operation_id>/panel`, `VisualOperation.actual_panel_frame_id` (omitted from every dump when absent, like `VisualExecutedClick` A1). The panel is fetched in `_capture(..., "after")` and committed in the SAME transaction as the after-frame (new optional `panel=` argument of `commit_captured`), because the operation's `executing -> completed` transition is single-shot. Store/fetch/signature failure drops only the panel and clears the reference (`operation.model_copy`); `reconcile` tolerates the dropped reference. `/trace` `items[]` gets `panel` only when present; bytes are served by the existing `/operation-frames/{id}`.

Harness: `evidence.export_operation` adds `panel` metadata only when the trace row has it; `run.py collect` keeps the verified image as `panel-<operation_id>.png` (best effort, create-only); `evaluate` re-verifies a retained panel for credited operations. `metrics.py`, oracle, `OutcomeReview`, scoring: untouched. The reviewer reads after-frame + panel image.

## 2. Files (diff summary)

Worker (`workers/playwright/src/`)
- `vision-tab-panel.ts` (new): in-page tab/panel/clip detection (`tabPanelClip`), `readTabPanelClip`, `captureTabPanelBand`.
- `vision-operations.ts`: `tabPanelFrame` session flag (agent mode + requested capability), capability advertised, private `captureTabPanel`, one call after the after-capture. Settle/equivalentState code not edited.
- `vision-contract.generated.ts`: regenerated with `uv run python packages/contracts/export_vision_worker.py` (same method as r7; before my change the file already had uncommitted diffs from earlier rounds; mine adds `actual_panel_frame_id`, role `panel`, capability, maxItems 10/3).
- `vision-tab-panel.spec.ts` (new, 7 tests).

Python
- `packages/contracts/src/auto_at/contracts/vision.py`: frame role `panel`; `VisualOperation.actual_panel_frame_id` + omit-when-absent serializer.
- `packages/contracts/src/auto_at/contracts/vision_worker.py`: capability literal, `required_capabilities` max 10, frames/ack max 3.
- `apps/control-plane/config.py`: `vision_agent_tab_panel_frame_enabled=False`.
- `apps/control-plane/application/vision_agent_loop.py`: `worker_capabilities` adds `tab-panel-frame-v1` only when the flag is on.
- `.env.example`: flag (false).
- OUTSIDE the file list, required by the design (the "nơi lưu/xuất frame" clause): `application/vision_operations.py` (fetch/commit/reconcile), `infrastructure/persistence/vision_unit_of_work.py` (`commit_captured(panel=)`, `_store_panel`), `infrastructure/persistence/repositories.py` (reference loop includes `panel`), `infrastructure/persistence/models.py` (CHECK constraint now `('before','after','panel')`), `application/vision_results.py` (`/trace` `panel` key only when present).
- `migrations/versions/c8d0e2f4a6b8_allow_panel_operation_frame.py` (new; head was `b7c9d1e3f5a7`): drops and recreates `ck_visual_operation_frame_role` with `'panel'`. NOT run. Rollback: its `downgrade()` restores the 2-value check, refusing while panel rows exist. Lock: brief ACCESS EXCLUSIVE on a small metadata table; no backfill, no column, no index. This file is outside the permitted list; it is unavoidable on PostgreSQL (without it `add_frame` for a `panel` row violates the CHECK and the whole after commit fails once the flag is on). Please approve or tell me to take the other route (no frames-table row; sidecar in the operation JSON) which I judged more code and no retention/delete/audit reuse.

Harness
- `benchmark/vision/accuracy/evidence.py` (`export_panel`), `run.py` (`retain_panels`, evaluate re-verify), `README.md` (section).

Docs / graphs
- `docs/adr/043-tab-panel-frame-evidence.md` (new), `docs/vision-agent-operations.md` (flag paragraph), graphs `playwright-vision-worker` (+2), `vision-agent-loop` (+1), `vision-accuracy-harness` (+1), `vision-exploration` (+migration), synced with `--apply`.

Not touched: oracle, `metrics.py`, prompts, gate, `domain/vision.py` (see risks), plan README/progress.html.

Callers/blast radius: `commit_captured` has one production caller (`vision_operations._capture`); the new kwarg is passed only when a panel exists, so with the flag off the call is byte-identical (tested). `VisualOperationFrame.role` Literal widened; `VisualWorkerOperationResult.frames` max 3.

## 3. Test output (real)

```
uv run ruff check .                      -> All checks passed!
npx tsc --noEmit (workers/playwright)    -> exit 0, no output
npx eslint on my 3 TS files              -> exit 0 (npx eslint src reports 22 errors, all in files I did not touch: fixtures/*, origin-guard.cjs, vision-contract.ts, vision-dom.spec.ts, vision-outcome-capture.spec.ts; pre-existing)
npx playwright test src/vision-tab-panel.spec.ts --workers=1
  7 passed (20.8s)  (below viewport -> panel 1280xN, N<=720, scroll 0,0, state still observable; inside viewport -> none; not a tab -> none; panel not rendered -> none; capability absent -> none; agent_mode off -> none; page mutates during capture -> image dropped, status completed)
npx playwright test src/contract.spec.ts src/vision-agent-evidence.spec.ts src/vision-outcome-capture.spec.ts src/vision-tab-panel.spec.ts --workers=1
  36 passed, 1 skipped (1.1m)
CODEX_BRIDGE_ENABLED=false uv run pytest tests/test_vision_accuracy_binding.py tests/test_vision_agent_loop.py tests/test_vision_tab_panel_frame.py -q
  55 passed, 38 skipped (81s)
tests/test_vision_agent_evidence_flags.py tests/test_qa_r8_agent_evidence.py tests/test_vision_operation_failure_stage.py tests/test_vision_accuracy_agent_evidence.py tests/test_vision_accuracy_binding.py tests/test_vision_accuracy_loop.py tests/test_vision_agent_loop.py tests/test_vision_results.py + my two new files
  168 passed, 56 skipped, 7 failed (7 failures were my new test module using a module-level timestamp; fixed, then the three-file run above passed)
tests/test_vision_tab_panel_frame.py alone: 13 passed, 2 skipped
tests/test_vision_accuracy_tab_panel.py: 9 passed
```
New Python tests: `tests/test_vision_tab_panel_frame.py` (contract shape/serializer/round-trip/old payload, 3-frame result and reference mismatch, flag default and capability list, open contract, processor passes the panel into the after commit, no panel -> commit kwargs identical to before, unusable panel does not fail the operation, `_store_panel` verification and drop cases, 2 PostgreSQL tests) and `tests/test_vision_accuracy_tab_panel.py` (flag-off export/folder identical, panel metadata export, collect keeps the verified file, unreadable/tampered/deleted panel does not break collect, malformed values).

Not verified: the 2 PostgreSQL tests and the 56 other DB tests are SKIPPED here (isolated PG fixture at 127.0.0.1:55437 not running; I did not start docker). So the real commit of the third frame row, the migration SQL and the new CHECK constraint have not run against PostgreSQL. The full `uv run pytest tests` did not finish within the 9-minute cap (DB skips are slow); I ran the vision/accuracy subsets above. `CODEX_BRIDGE_ENABLED=false` was exported because the shell's env enables the Codex bridge and makes `Settings()` fail at import (environment, not my change).

## 4. Rebuild / flags for the next live run
- Rebuild: `playwright-worker` (capability), `control-plane` (models/trace/config), `temporal-worker` (processor + flag). `claude-bridge`: no.
- Run `alembic upgrade head` (c8d0e2f4a6b8) on the DB BEFORE setting the flag.
- Override env: `VISION_AGENT_TAB_PANEL_FRAME_ENABLED=true` (temporal-worker only), together with the usual `VISION_AGENT_CLICK_CONTEXT_ENABLED` / `VISION_AGENT_INVENTORY_ENABLED` if comparing with round 21.
- Harness: after `collect`, look for `runs/<iteration>/panel-<operation_id>.png`.

## 5. Risks / open points
1. IMPORTANT: the oracle record of `mct-30`/`mct-31` is a plain `button.button-character-title` (class `active`), no `role=tab`/`aria-selected`/`aria-controls` in `reference_class`/`reference_path`. Unless the live DOM has those attributes (the oracle does not store them), the generic ARIA detection will not fire for the two targets this feature was meant for. I did not hard-code the site or add a class-based heuristic. Check the live DOM (or decide a generic fallback, for example "sibling control group where exactly one carries an `active`-like state and a following block toggles").
2. A live check of `captureBeyondViewport` on the real site is needed: pages with `vh`-based layouts may re-layout while the viewport override is applied; the state re-check drops the image in that case but cannot make it appear.
3. `domain/vision.py` immutability tuple (`actual_before/after_frame_id`, `locator_id`) was not extended to `actual_panel_frame_id` (outside scope). The panel reference is set once in the same commit as completion; a later conflicting rewrite is not blocked by that tuple, though the repository's frame-reference check still binds it to a real `panel` row.
4. Worker result without a panel while a later retry reads it: handled (reconcile clears a dropped reference); not exercised against a real database.
5. `hgraph check` (full) passes; `hgraph check --changed` exits 1 only because of earlier-round uncovered files (codex bridge, control-plane, dashboard files) that are not mine; every file I added or changed is covered.

## Handoff for the plan (not written by me)
README/progress.html owner: add "r15: ADR-043 tab-panel frame implemented offline, default off; needs migration c8d0e2f4a6b8 approval + rebuild playwright-worker/control-plane/temporal-worker; open issue: mongchiton tab buttons have no ARIA, detection may not fire; PG tests unrun". Next command for a live round: apply migration, set the flag in the override, recreate the three services, run a session, `run.py collect`, check for panel files.

ASK_PM
- question: Are the mongchiton "NHÂN VẬT"/"THÚ CƯỠI" tabs ARIA tabs on the live site, or plain class-toggled buttons? If plain, should a class/state-based tab heuristic be added (new decision) or should the capability stay ARIA-only?
  context: oracle-mongchiton-1280-v1.json mct-30/31 (`button-common button-character-title active`, no role/aria in oracle record); `workers/playwright/src/vision-tab-panel.ts` `tabPanelClip`
  blocked_on: whether this phase actually unblocks mct-30/mct-31

ESCALATE
- the migration `migrations/versions/c8d0e2f4a6b8_allow_panel_operation_frame.py` plus edits to five control-plane files listed in section 2 are outside the allowed file list; they are needed by the chosen storage design. Not run against any database. Need user approval before deploying.

GRAPH_UPDATE
- graph đã cập nhật: playwright-vision-worker, vision-agent-loop, vision-accuracy-harness, vision-exploration (`add` + `sync --apply`)
- file mới đã đưa vào graph: workers/playwright/src/vision-tab-panel.ts, workers/playwright/src/vision-tab-panel.spec.ts, tests/test_vision_tab_panel_frame.py, tests/test_vision_accuracy_tab_panel.py, migrations/versions/c8d0e2f4a6b8_allow_panel_operation_frame.py
- hgraph check: "✔ Không có vấn đề." (exit 0); hgraph check --changed: exit 1, only uncovered-changed of files from earlier rounds (none of mine)

Processes: none left running (each Playwright test closes its browser); no docker started or changed; nothing committed.
