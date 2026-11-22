STATUS: DONE
# QA report - ADR 045

## QA VERDICT (vòng 2): PASS
(Vòng 1: FAIL - xem bên dưới; vòng 2 ở cuối file.)

## Commands (cwd `auto-at-ui/workers/playwright` unless noted)
- `npx playwright test src/vision-dom.spec.ts -g "sliding|never stops|static visual button" --repeat-each=5` -> 24 pass / 1 fail of 25 (`s4-qa-new5x5.log`)
- `... -g "out of the viewport" --repeat-each=30` (parallel workers) -> 8 pass / 22 fail (`s4-qa-outvp30.log`)
- `... -g "out of the viewport" --repeat-each=20 --workers=1` -> 18 pass / 2 fail (`s4-qa-outvp20-w1.log`)
- `npx playwright test src/vision-dom.spec.ts src/vision-visual-buttons.spec.ts --repeat-each=5` -> 228 pass / 2 fail, both TC-03 (`s4-qa-files5x.log`)
- `npx tsc --noEmit` -> exit 0 (`s4-qa-typecheck.log`)
- `npx eslint src` -> 22 errors, all `no-explicit-any`, none on lines added by this change (`s4-qa-lint.log`)
- `uv run python benchmark/vision/codex/run_offline.py -q --tb=short tests/test_codex_bridge_benchmark.py -k manifest --basetemp=.pytest-artifacts/tmp-qa` (cwd auto-at-ui) -> 1 passed, 9 deselected (`s4-qa-manifest.log`)

## Flaky rate
- TC-01, 02, 04, 05: 0 failures in 5 repeats each (stable).
- TC-03 (slide out of viewport): flaky. 1/5, 10% with 1 worker, 73% under parallel load.

## Findings (blocking)
1. TC-03 `vision-dom.spec.ts:271-275` - expected rejection `state_changed_during_observation`, actual: `observeDom` resolved with the link bound, skipped 0, binding x ~ 0.74-0.86 of the viewport (the link was still on screen). The test depends on timing: the link (3000 px / 1000 ms) leaves the 1280 px viewport only after ~430 ms, and `observeDom` can finish before that, so no state change is seen. A test that depends on a race is not acceptable. Fix the test to be deterministic (for example, move the link out immediately/with a short, steep transition or jump it out at a controlled point, or wait/hold observation until it is off-screen), or if the product is meant to detect this, fix the product. Developer must decide which; cannot tell from the spec alone. Note: developer reported green, so it was likely run on a quiet machine.
2. Graph gate: `hgraph check --changed` -> `[uncovered-changed] workers/playwright/src/vision-dom.spec.ts, vision-dom.ts` (not in any graph). Developer must run `hgraph add <slug> <file>` (or `hgraph sync <slug> --apply`) and re-check.

## Not tested
- Full Python suite (32 min) not rerun, per instruction; relies on developer log `.pytest-artifacts/s4-fix-python.log`.
- Live-site A/B harness (impact H6) - needs a live session, out of scope.
- ElementHandle leak is judged by code review only (wait loop uses locator `boundingBox`, no handle); the suite has no explicit leak assertion.
- Pre-code-fix red state not re-verified by QA (developer log `s4-fix-red.log`).
- Stress test: not needed - polling is bounded (1200 ms, 50 ms interval) and per skipped visual button only; the 10 s never-stops case is covered by TC-04.

## Process note
During the run QA mistakenly ran `git stash` (a stray command) and immediately `git stash pop`; the three tracked files are restored (diff stat 120+/11-, identical), stash list empty. The manifest test was re-run after the restore (result above). Please confirm with `git diff --stat` if in doubt.

## Secrets
`qa/` contains only test tables and logs summaries; no secrets.

# Vòng 2

Sau khi developer làm TC-03 xác định (lớp phủ 1280 px), thêm timeout 250 ms cho `read()` và test "removed while waiting for motion".

| Lệnh | Kết quả | Log |
|---|---|---|
| 6 test chuyển động, `--repeat-each=20 --workers=1` | 120 pass / 0 fail (0% flaky) | s4-qa2-motion-w1.log |
| như trên, `--workers=4` | 120 pass / 0 fail | s4-qa2-motion-w4.log |
| `vision-dom.spec.ts` + `vision-visual-buttons.spec.ts`, `--repeat-each=3` | 141 pass / 0 fail | s4-qa2-files.log |
| `tsc --noEmit` | exit 0 | s4-qa2-typecheck.log |
| manifest drift (`-k manifest`) | 1 passed, 9 deselected | s4-qa2-manifest.log |
| `hgraph check` (đầy đủ) | "Không có vấn đề" | - |
| `hgraph which` vision-dom.ts / vision-dom.spec.ts | cả hai -> playwright-vision-worker | - |

Cổng graph: `hgraph check --changed` báo `uncovered-changed` là hạn chế của tool (tiền tố đường dẫn `auto-at-ui/...` vì git root là thư mục cha), không phải lỗi graph. `hgraph check` đầy đủ sạch và `which` xác nhận cả hai file đã thuộc graph. Không chạy `hgraph add`.

Vòng 2 không dùng git stash, không đổi cây làm việc. Vẫn chưa chạy: suite Python đầy đủ, A/B live, assert rò handle (xem trên).
