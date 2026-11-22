STATUS: DONE

CONTEXT_CHECK
- conventions: docs/code-standards.md (hgraph brief), r15 report section 2 as the file list
- graphs: playwright-vision-worker, vision-agent-loop, vision-accuracy-harness, vision-exploration (read, synced)
- blast radius: only reverts r15 hunks; no new code

## Impact inventory
Database: not touched (migration c8d0e2f4a6b8 was never run; file removed). Alembic head is `b7c9d1e3f5a7` again (no migration has it as down_revision).

## Shelved
Location: `auto-at-ui/.pytest-artifacts/r15-shelved/`
- `new/`: workers/playwright/src/vision-tab-panel.ts, vision-tab-panel.spec.ts, migrations/versions/c8d0e2f4a6b8_allow_panel_operation_frame.py, docs/adr/043-tab-panel-frame-evidence.md, tests/test_vision_tab_panel_frame.py, tests/test_vision_accuracy_tab_panel.py (copied, byte-checked with cmp, then deleted from tree)
- `with-r15/`: 20 pre-edit copies of files r15 edited
- `r15.patch`: 20 file diffs (gone-state to with-r15); `git apply --check --ignore-whitespace` passes on the current tree
- `README.md`: restore steps

## Reverted hunks (only r15's)
- vision_agent_loop.py: capability line; vision_operations.py (app): `extra`/`**extra`, `_fetch_panel`, reconcile panel clause; vision_results.py: `/trace` panel key; config.py flag; models.py CHECK back to ('before','after'); repositories.py loop back to before/after; vision_unit_of_work.py: `panel=` arg, `_store_panel`, panel add_frame
- contracts vision.py: `actual_panel_frame_id` + serializer, role Literal; vision_worker.py: capability literal, required_capabilities max 9, ack/frames max 2 (`model_serializer` import kept: A1 uses it)
- worker vision-operations.ts: import, `tabPanelFrame`, capability list, `captureTabPanel`, call site
- vision-contract.generated.ts: regenerated with `uv run python packages/contracts/export_vision_worker.py`; no `panel` left
- benchmark evidence.py (`export_panel`), run.py (`retain_panels`, evaluate re-verify), README section; .env.example flag; docs/vision-agent-operations.md paragraph
- graphs: removed r15 file entries (hgraph rm) and `sync --apply` on the 4 graphs; graph prose had no panel sentences

## Verification
- grep `tab.panel|tab_panel|actual_panel_frame|c8d0e2f4a6b8|ADR-043|043-tab` over apps packages workers/playwright/src benchmark migrations docs tests .env.example (excluding node_modules/.next/__pycache__/runs): empty
- Still present: BOX_CENTER_TOLERANCE_PX (vision-checkpoints.ts:22), isPresentationOnlyAnimated, `agent-loop-v2`, RECEIPT_CLOCK_SKEW (spool.py:43), A1 context fields (vision.py:357), A1/A2/A3 flags in .env.example
- `uv run ruff check .` -> All checks passed!
- `CODEX_BRIDGE_ENABLED=false uv run pytest` (test_vision_contracts, test_vision_worker_contracts, test_agent_loop_contracts, test_vision_agent_evidence_flags, test_qa_r8_agent_evidence, test_vision_operation_failure_stage, test_vision_operation_transport, test_vision_accuracy_{agent_evidence,binding,loop,metrics}, test_vision_agent_loop(+_qa), test_vision_results, test_qa_r9_bridge_receipt, test_qa_r11_agent_loop_prompt) -> `500 passed, 69 skipped in 182.74s` (skips = PostgreSQL-dependent tests, no DB running)
- `npx tsc --noEmit` (workers/playwright) -> exit 0
- `npx playwright test` vision-settle-animation.spec, vision-settle-animation.qa.spec, vision-agent-evidence.spec, vision-outcome-capture.spec, contract.spec `--workers=1` -> `67 passed, 1 skipped (1.7m)`
- `hgraph check` -> "Không có vấn đề."

## Notes
- r15 ESCALATE (migration approval) and ASK_PM (mongchiton tabs ARIA) are now moot while shelved; restore via `.pytest-artifacts/r15-shelved/README.md`.
- No processes left running; nothing committed; no docker; no migration run.

GRAPH_UPDATE
- graph đã cập nhật: playwright-vision-worker, vision-agent-loop, vision-accuracy-harness, vision-exploration
- file mới đã đưa vào graph: không có (chỉ gỡ 6 file r15)
- hgraph check: ✔ Không có vấn đề.
