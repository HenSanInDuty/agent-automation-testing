# Test cases - ADR 045 (observe moving visual buttons)

Runner: Playwright test, cwd `workers/playwright`. Spec: `src/vision-dom.spec.ts` (lines 224-298), `src/vision-visual-buttons.spec.ts`.
Result column = QA run on 2026-11-22 (logs in `.pytest-artifacts/s4-qa-*.log`).

| ID | Goal | Steps | Expected | Type | Result |
|---|---|---|---|---|---|
| TC-01 | Slide under a non-control layer (impact H1) | `observeSliding(default)`: link translateX 500px/1000ms under an inert cover; `observeDom` scope visual_buttons | elements == ["Play"], skipped 0, binding x ~ 600/1280, event `motion_regrounded` (info, motion_regrounded 1), log has no "Play", "/play", dom_path | auto (`sliding under a non-control layer`) | PASS 5/5 |
| TC-02 | Slide under another control (H2) | Same, cover has `cursor:pointer` | bound, skipped 0 | auto | PASS 5/5 |
| TC-03 | Slide out of viewport (H3) | distance 3000px | observeDom rejects `state_changed_during_observation`, no snapshot | auto | FAIL (flaky: 1/5, 22/30 parallel, 2/20 with --workers=1) |
| TC-04 | Never stops (H4) | 500px over 10 s | skipped 1, elapsed in [1100, 4000) ms, `coverage_limited` motion_waits 1 / regrounded 0, no regrounded event | auto | PASS 5/5 |
| TC-05 | Static page, no wait (H5) | distance 0 | skipped 1, elapsed < 1000 ms, motion_waits 0 | auto | PASS 5/5 |
| TC-06 | Regression: scope all/buttons unchanged | Whole `vision-dom.spec.ts` + `vision-visual-buttons.spec.ts`, 5 repeats (guard `interactionScope === "visual_buttons"` in vision-dom.ts) | no new failures | auto | PASS except TC-03 (228 pass, 2 fail = TC-03) |
| TC-07 | No ElementHandle leak | Tests dispose `anonymousTargets` and `document`; code review: wait only calls `resolveDescriptor(...).boundingBox()` (locator, no handle) | no handle created in the wait loop | auto+review | PASS (review; no leak assertion in suite) |
| TC-08 | Log does not expose control identity | Assert on captured JSON events (TC-01) | no name, href, dom path | auto | PASS (TC-01 assertion) |
| TC-09 | Typecheck | `npx tsc --noEmit` | exit 0 | auto | PASS |
| TC-10 | Lint | `npx eslint src` | no new errors | auto | 22 errors, all `no-explicit-any` at pre-existing lines (spec 319-356 etc.); none in the new block or vision-dom.ts - not attributable to this change |
| TC-11 | Manifest hash drift | `run_offline.py ... -k manifest` | pass | auto | PASS (1 passed, 9 deselected) |
| TC-12 | Full Python suite | not rerun (32 min); developer log `s4-fix-python.log` (136 pass) | - | manual/not rerun | NOT RUN |
| TC-13 | Live-site A/B (H6), 0 skip over 30 scans | needs live session | - | manual | NOT RUN (out of QA scope) |
| TC-14 | Graph gate | `hgraph check --changed` | clean | auto | FAIL: uncovered-changed vision-dom.ts, vision-dom.spec.ts |

Vòng 2: TC-03 PASS (120/120 w1, 120/120 w4 cùng 5 test khác và test mới 'removed while waiting for motion'); TC-06 141/141; TC-09 PASS; TC-11 PASS; TC-14 PASS qua `hgraph check` đầy đủ (hạn chế tool với --changed).
