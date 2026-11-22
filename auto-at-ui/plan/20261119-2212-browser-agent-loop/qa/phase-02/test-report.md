# Test report - Phase 2 (QA r1)

QA VERDICT: PASS

Moi truong: Windows 11, Node + Playwright 1.50.1 Chromium that, `workers/playwright`, `--workers=1`. Khong dung DB / docker / mang ngoai (fixture loopback 2 origin).

## Bang chung (output that, log o scratchpad cua QA)
- `vision-agent-mode.spec.ts` (dev): `23 passed (2.3m)`.
- `vision-agent-mode.qa.spec.ts` (QA, moi): `18 passed (1.2m)` chay 3 lan lien tiep (x3 deu 18 passed, exit 0). Lan dau tao spec co 6 loi do loi cua chinh test QA (min wait 100ms, text max 1000, op prepared de lai `operation_pending`, snapshot khong liet ke input submit); da sua test, khong phai bug san pham.
- `vision-operations.spec.ts`: `99 passed (6.2m)` - bang baseline phase 0 r2 (99 passed).
- 14 spec con lai (dom, history, locators, target-preflight, visual-buttons, readiness, outcome-capture, contract, vision, observability, click-evidence, sample-guard, settle-observability, observability): `140 passed, 1 skipped` (skip = `contract.spec.ts:120`, chi chay trong image).
- `npm.cmd run typecheck`: exit 0.
- `npm.cmd run lint`: exit 1, `22 problems (22 errors)` trong dung 6 file: `fixtures/exploration-strategy-benchmark.ts`, `fixtures/vision-integration-server.ts`, `origin-guard.cjs`, `vision-contract.ts`, `vision-dom.spec.ts`, `vision-outcome-capture.spec.ts`. `git status` ca 6 file: khong sua -> do san, khop so lieu dev. Khong loi o `vision-operations.ts`, `vision-agent-mode.spec.ts`, `fixtures/agent-loop-target.ts`, `vision-agent-mode.qa.spec.ts`. Luu y: baseline phase 0 khong co log lint worker (chi dashboard + ruff); ket luan "do san" dua tren file khong bi sua.
- v4 khong doi: spec v4 khong bi sua (`git status`), toan bo xanh voi `agent_mode` omitted; cac nhanh agent doi chung v4 (T06, T16, T21, T26-T28) deu giu hanh vi cu.

## Coverage theo yeu cau
Stale snapshot / evict (T01-T05), K3 allowlist (T08-T10), blocklist + submit/download/Enter (T11-T18), re-baseline batch (T19-T21), K4 dialog/download (T22-T28), back/navigate explore (T07), v4 khong doi (T06, T16, T21, T28, T29, T30). Tong 33 muc; 41 test Chromium moi (23 dev + 18 qa) + 239 test hoi quy, 0 fail.

## Hanh vi can leader biet (khong phai FAIL)
1. Tu khoa chi NFC + lowercase, KHONG bo dau: `"nap the"` khong chan nhan `Nạp thẻ` (T14). Danh sach `blocked_action_terms` phia Python (phase 4) phai chua ca dang co dau/khong dau neu muon chan ca hai.
2. Khop kieu "chua" -> "xoa" chan ca "Xoa bo loc" (quyet dinh danh sach o phase 4). Worker khong tu chan tu khoa rong: contract Python gioi han `min_length=1` (vision_worker.py:52) nen khong bi chan toan bo, nhung worker khong kiem tra lai (tu khoa " " hoac 1 ky tu se khop rat rong).
3. Snapshot DOM vision-dom da loc bo `input[type=submit|reset|image]` khoi danh sach element, nen agent khong tham chieu duoc chung; chan cau truc van la lop phong thu thu hai (T12 chung minh voi `button[type=submit]`).
4. Dev bao test 20 vong thay 25 do `operation_budget`=22 voi 3/2: da kiem, nhat quan voi cong thuc giu nguyen cua plan.

## Chua test duoc
- Target mongchiton that (phase 6): chan nham tu khoa tren control that.
- `vision-dashboard.spec.ts`, `dashboard-auth.spec.ts`, `generation-provider-settings.spec.ts`: khong import `vision-operations`, ngoai blast radius phase nay, khong chay.
- Control `role=button` kieu `div` gui form bang JS (khong co `type=submit`): worker khong phat hien duoc, chi phu thuoc tu khoa; khong test.
- Redirect 30x sang origin ngoai trong cung tab: chua co fixture; kiem URL song o prepare nen nhieu kha nang xu ly, nhung chua chung minh bang test.
- Python/pytest: phase khong dung Python.

Stress test: khong can - khong co query/lock/job hang loat moi; vong 20 observe/click da nam trong spec dev.

## Cong graph
`hgraph add playwright-vision-worker workers/playwright/src/vision-agent-mode.qa.spec.ts` -> "Da them 1 file ... (tong 28)", roi `hgraph sync playwright-vision-worker --apply`. `hgraph check`: `4 graph, 445 file source / Khong co van de` (exit 0). `hgraph check --changed`: exit 1, `uncovered-changed` 14 file: 12 file phase 1 (Python control-plane/contracts/tests) chua thuoc graph + `vision-operations.ts`, `vision-contract.generated.ts` (bao nham do tien to `auto-at-ui/` khi git toplevel la thu muc cha; `hgraph check` thuong xac nhan hai file nay trong graph). Khong con file nao do phase 2 tao/sua bi bao thieu graph. Cung tinh trang phase 1 (user da chap nhan coi la loi tien to duong dan).

## Phan quyet
Tieu chi xong phase 2: typecheck sach, spec agent mode xanh, hoi quy xanh, v4 khong doi. Lint worker do san 22 loi, khong thuoc phase nay. QA VERDICT: PASS.

Tai lieu: `plan/20261119-2212-browser-agent-loop/qa/phase-02/test-cases.md`, file nay, automation `workers/playwright/src/vision-agent-mode.qa.spec.ts`.
