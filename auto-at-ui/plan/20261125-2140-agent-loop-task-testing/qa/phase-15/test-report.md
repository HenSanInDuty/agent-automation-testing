STATUS: PASS
QA VERDICT: PASS

# QA phase 15 r1 - dashboard yeu cau/duyet ban nhap

## Output that (chay doc lap)
```
apps/dashboard: npm run typecheck -> exit 0 ; npm run lint -> exit 0 (khong loi)
apps/dashboard: npm test -> tests 77, pass 77, fail 0
workers/playwright: npm run typecheck -> exit 0 (sau khi them ca QA)
CODEX_BRIDGE_ENABLED=false uv run pytest tests/test_dashboard_route_contracts.py -q -> 27 passed, 1 warning
spec day du (wrapper scratchpad, next dev cong 3207, --workers=3) -> 79 passed (4.1m), exit 0
   (59 ca cu + 20 ca phase 15, 0 fail)
3 ca QA them (-g "QA phase 15") -> 3 passed (9.7s)
hgraph check -> 8 graph, 555 file source / Khong co van de
```
Sau khi xoa 1 assertion thua (tu so sanh voi chinh no) khoi ca QA T07, chi chay lai typecheck, khong chay lai ca do (xoa dong khong anh huong logic; ca van pass lan truoc voi dong do).

## GRAPH
`hgraph check` sach. `hgraph check --changed` van exit 1 (uncovered-changed, 64 file, ten co tien to `auto-at-ui/`): false positive da biet (file tracked chua commit, xem memory "hgraph from auto-at-ui"). `hgraph which` xac nhan agent-task-draft-panel.tsx, agent-task-draft-model.ts, generation-dashboard.tsx, generation-api.ts thuoc graph `vision-dashboard`. Khong phai loi cua phase nay.

## Kiem tay bang trinh duyet (du lieu gia, Chromium qua Playwright; khong dung localhost:1000)
- Screenshot: `qa/phase-15/qa-form-filled.png`, `qa-form-sent.png`, `qa-review-before-ack.png`, `qa-review-409.png`, `qa-review-404.png`.
- Man duyet hien day du source gom gia tri `Zx9!hunter2-sample` (khong an), hash, assessment advisory, provenance, nhom Test values, stop_conditions.
- Gia tri chi xuat hien trong 1 POST `/vision/explorations/{id}/test-draft`; khong o URL, storage, cookie, console, pageerror, DOM/input sau khi gui; khong host ngoai.
- Nut duyet vo hieu den khi tick; 409/404 hien thong bao ro, dialog dong.
- Luu y nho (khong FAIL): anh fullPage cua man duyet co thanh dieu huong sticky chen giua trang - la hien tuong cua screenshot fullPage, khong phai loi.

## Thay doi cua QA (code test, trong pham vi spec cua phase)
Them 3 ca "QA phase 15: ..." cuoi `workers/playwright/src/vision-dashboard.spec.ts` (privacy request/host/console, screenshot 409, 404). Khong sua code san pham.

## Stress test
Khong can - chi doi UI, khong vong lap tap lon/query/lock.

## Chua test duoc / han che
- Chay voi API gia (route mock), khong voi backend that; hop dong BE da phu boi pytest route contracts.
- "Do dai mong doi" cua buoc type chua hien (developer da neu ASK_PM, can BE them text_chars) - khong nam trong tieu chi xong 1-6.
- Danh sach buoc bi loai: BE tu choi ca draft, FE hien stop_conditions (quyet dinh developer 7, leader soat).
- Panel dat tren VisionSessionDetail, khong "ngay canh" panel assessment (do pham vi cam); nut tieng Anh "Create test draft".
- Chi chay Chromium; khong kiem tra autofill that cua trinh duyet (chi thuoc tinh autocomplete=off).
- Khong lap lai ban fail-before-fix (day la feature, khong phai fix).

## Tai lieu
- `plan/20261125-2140-agent-loop-task-testing/qa/phase-15/test-cases.md`
- file nay; automation: `workers/playwright/src/vision-dashboard.spec.ts`, `apps/dashboard/app/**/*.test.ts`
- Tien trinh: dev server cong 3207 da dung (khong con LISTEN). Khong commit.
