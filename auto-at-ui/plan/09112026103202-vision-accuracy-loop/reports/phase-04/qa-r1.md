STATUS: PASS
QA VERDICT: PASS

Tóm tắt (chi tiết: `plan/09112026103202-vision-accuracy-loop/qa/phase-04/test-report.md`, `test-cases.md`):
- ruff sạch; pytest agent loop + QA + live persistence 219 passed (Postgres cô lập qa-r1-vision-pg, đã dừng); tsc sạch; playwright 3 spec 143 passed (141 + 2 QA mới), không flaky.
- (a) refresh đọc-chỉ off-origin thành công, không click/POST; (b) click, type, scroll, navigate, wait explore, wait setup không cờ, refresh explore, refresh kèm proposal/snapshot/locator/restore/replay đều bị chặn; (c) trong-origin không đổi; (d) chuỗi r5 -> agent_done; (e) không settle -> state_mismatch, refresh bị chặn trên (2); (f) hồi quy xanh.
- Automation thêm: QA-W20, QA-W21 trong `workers/playwright/src/vision-agent-mode.qa.spec.ts`.
- Graph: `hgraph check --changed` báo 48 uncovered-changed, gồm `workers/playwright/src/vision-operations.ts` (nợ cũ, worker TS ngoài graph); không có drift/stale. Phiên chính quyết định có xử lý không.
- Chưa test: phiên live thật (cấm); đỏ->xanh của test control-plane (FakeWorker), phủ bằng worker spec.
- Cần rebuild playwright-worker trước phiên live kế tiếp.
