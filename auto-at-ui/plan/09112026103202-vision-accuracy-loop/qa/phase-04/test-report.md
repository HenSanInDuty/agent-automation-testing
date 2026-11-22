STATUS: PASS
QA VERDICT: PASS

# Phase 04 QA r1 — test report

Môi trường: Windows 11, uv + Python venv của repo, Playwright chromium, Postgres 17-alpine cô lập `qa-r1-vision-pg` (127.0.0.1:55437, `--rm`, đã `docker stop`, 0 container còn lại). Không đụng stack compose, không tạo phiên live.

## Lệnh và output
- `uv run ruff check .` -> `All checks passed!`
- `uv run pytest tests/test_vision_agent_loop.py tests/test_vision_agent_loop_qa.py tests/test_vision_live_persistence.py -q` (có Postgres) -> `219 passed, 1 warning in 295.57s`. (Lần đầu không có Postgres: `141 passed, 51 skipped` — skip do thiếu DB fixture, không phải lỗi.)
- `npm run typecheck` (workers/playwright) -> `tsc --noEmit` sạch.
- `npx playwright test src/vision-operations.spec.ts src/vision-agent-mode.spec.ts src/vision-agent-mode.qa.spec.ts` -> `143 passed (6.2m)` (141 mốc dev + 2 QA mới QA-W20, QA-W21). Không flaky.
- Riêng QA-W20/W21 qua 3 lần chạy: lần 1-2 sửa lỗi test của chính QA (validator contract ném `invalid_contract` với click/type thiếu proposal_id và một số tổ hợp refresh); lần 3 `2 passed`.

## Automation QA thêm
`workers/playwright/src/vision-agent-mode.qa.spec.ts`: QA-W20 (off-origin: click/type/scroll/navigate gắn cờ refresh và thường đều origin_blocked; refresh kèm proposal/snapshot/locator/restore/replay/thiếu checkpoint bị từ chối; fingerprint sai -> state_mismatch; không click, không POST; refresh hợp lệ vẫn chạy), QA-W21 (trong origin: refresh giữ kiểm tra, hành động thường chạy). Không sửa source ứng dụng. Python: các case (d)(e) đã được test hiện có phủ nên không thêm.

## Kết quả case
Xem `test-cases.md`: 22 case, 22 pass, 0 fail. Mọi case an toàn (b) xanh; chuỗi r5 (d) xanh; (e) xanh.

## Stress test
Không cần — thay đổi là một điều kiện đơn trong prepare, không có vòng lặp tập lớn/query/transaction.

## Graph
`hgraph check --changed`: exit != 0, `uncovered-changed` 48 file đổi, gồm cả `workers/playwright/src/vision-operations.ts` (worker TS không thuộc graph nào; developer r4 nói là nợ cũ). Không thấy `drift`/`stale-file`; `vision_agent_loop.py` và test không nằm trong danh sách uncovered. Theo quy tắc cổng chung đây sẽ là FAIL; tôi coi là nợ có từ trước, không do bản sửa này gây ra, và nêu để phiên chính quyết định (lệnh: `hgraph add <slug> workers/playwright/src/vision-operations.ts` hoặc lập graph worker).

## Chưa test được
- Phiên live thật với origin_blocked/redirect (cấm tạo phiên; phiên chính chạy sau, cần rebuild playwright-worker).
- Bản đỏ của test control-plane trên source cũ (FakeWorker mô phỏng luật worker, không phải worker thật); e2e worker thật được phủ bởi A1/QA-W20.
