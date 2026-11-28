# Phase 15 test cases (QA r1)

Spec = `workers/playwright/src/vision-dashboard.spec.ts` (du lieu gia, dev server cong 3207). Unit = `apps/dashboard` `npm test`.

| ID | Nhom | Tieu chi | Mo ta / mong doi | Test | Ket qua |
|---|---|---|---|---|---|
| T01 | Happy | 1 | Eligible, 2 buoc type: bao cao nhat quan, form theo thu tu, nut submit khoa den khi du gia tri, POST `{values}` + Idempotency-Key + CSRF | spec "an eligible agent session..." (L1107) | PASS |
| T02 | Bien/loi | 1 | Khong du dieu kien: hien ly do, khong nut tao, 390px khong tran ngang | spec L1152 | PASS |
| T03 | Loi | 1 | Bao cao 404 / khong doc duoc: khong nut, assessment van dung | spec L1169 | PASS |
| T04 | Bien | 1 | Khong co buoc type: khong textbox, gui `{values: []}`, 200 dung lai | spec L1179 | PASS |
| T05 | Loi | 1 | Ma loi API assessment_inconsistent / input_value_mismatch / input_value_not_allowed / credentials_in_source / input_value_missing / locator_unavailable: chu loi ro, khong lap gia tri, input xoa, state sach | spec L1200 (6 ca) | PASS x6 |
| T06 | Bao mat | 2 | Gia tri khong o URL, local/sessionStorage, cookie, console, DOM, input.value sau khi gui | spec T01 + T05 (`holdsNothing`) | PASS |
| T07 | Bao mat | 2 | (QA them) Gia tri chi nam trong DUNG 1 request POST test-draft; khong request khac (URL/body) chua gia tri; khong host ngoai localhost/dashboard; khong console/pageerror chua gia tri; storage sach ca luc dang go | spec "QA phase 15: typed value stays..." | PASS |
| T08 | Bao mat | 2 | input `autocomplete=off`, khong `name`, form autocomplete off | spec T01 | PASS |
| T09 | Happy | 3 | Man duyet draft contains_test_values: hien du source gom gia tri, hash, assessment advisory, nhat quan, nguon gia tri, stop_conditions | spec L1235 | PASS |
| T10 | Happy | 3 | Nut duyet vo hieu khi chua tick; tick -> duyet gui `acknowledge_disposable_credentials:true` | spec L1235 | PASS |
| T11 | Bien | 3 | Tu choi draft co gia tri: khong can xac nhan, khong gui truong | spec L1273 | PASS |
| T12 | Bien | 3 | Draft khong gia tri: khong hop xac nhan, khong gui truong | spec L1282 | PASS |
| T13 | Loi | 3 | 409 reviewer_must_differ_from_requester, disposable_credentials_ack_required, owned_test_target_disabled; 404 thieu quyen: thong bao ro, dialog dong, nut duyet bat lai | spec L1299 (4 ca) + QA screenshot 409/404 | PASS x4 (+2) |
| T14 | An toan | 3 | Khong co nut chay/execute moi o panel; tren man duyet chi co nut duyet san co | spec T01 L1116, L1261; QA test 2 | PASS |
| T15 | Responsive | - | Man duyet 390px khong tran | spec L1312 | PASS |
| T16 | Tiêu chí 4 | 4 | Kieu/API moi + test api/dashboard/model | `npm test` 77/77 | PASS |
| T17 | Tiêu chí 5 | 5 | typecheck, lint, npm test, pytest route contracts | chay lai doc lap | PASS |
| T18 | Hoi quy | - | 59 ca cu cua vision-dashboard.spec (planner v4/accuracy, Codex, click highlight...) | spec full 79/79 | PASS |
| T19 | Tiêu chí 6 | 6 | hgraph graph | `hgraph check` sach; `--changed` false positive tien to (xem report) | PASS (co ghi chu) |
