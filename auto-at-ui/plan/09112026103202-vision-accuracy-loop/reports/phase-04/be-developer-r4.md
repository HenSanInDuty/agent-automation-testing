STATUS: DONE

CONTEXT_CHECK
- conventions: AGENTS.md (qua docs/code-standards.md), docs/code-standards.md (đọc ở r3)
- graphs: vision-agent-loop (hgraph brief ở r3); worker TS không thuộc graph Python
- blast radius: 5 file bị phụ thuộc cho vision_agent_loop.py (r3); worker: chỉ spec worker

Database: không đụng.

## 1. Worker (workers/playwright/src/vision-operations.ts)
- Luật cũ (line 521-526): trang http(s) ngoài allowlist, agent mode: `requireVision(["close_popup","back"].includes(kind), "origin_blocked")`.
- Luật mới (line 521-529): thêm đúng một ngoại lệ `refresh = request.refresh_observation && request.purpose === "setup" && request.action.kind === "wait"`; `requireVision(refresh || ["close_popup","back"].includes(kind), "origin_blocked")`. Các ràng buộc còn lại của refresh (checkpoint_id, không proposal/dom_snapshot/locator/restore/replay) vẫn do `invalid_observation_refresh` ngay bên dưới kiểm tra; `expected_state_fingerprint == session.state.fingerprint` vẫn bắt buộc. Refresh chỉ settle trang, không click/type. Không đổi gì khác.

## 2. Spec worker (vision-agent-mode.spec.ts, test mới "only the read-only observation refresh may run outside the allowlist...")
Kịch bản: mở popup ngoài allowlist, đổi DOM popup (state cũ) -> `observeDom` ném `state_mismatch`; các prepare bị `origin_blocked` (wait explore thường, setup wait không cờ refresh, refresh với purpose explore, scroll/navigate gắn cờ refresh); refresh setup hợp lệ completed, `executed_click` null, observe lại thấy tên mới, không click (`dataset.clicked` undefined), không POST ngoài; sau đó click vẫn `origin_blocked`. Click/type off-origin vẫn được test cũ "a popup outside the allowlist..." chặn (không sửa).
- ĐỎ trên luật cũ: `Error: origin_blocked ... Expected "prepared", Received "rejected"` tại lần refresh (1 failed).
- XANH sau sửa: `ok 1 ... (1 passed)`.
- `npm run typecheck` (tsc --noEmit): sạch, không output lỗi.
- `npx playwright test src/vision-operations.spec.ts src/vision-agent-mode.spec.ts src/vision-agent-mode.qa.spec.ts`: `141 passed (6.0m)` (3 file gộp; agent-mode có thêm 1 test mới).

## 3. Control-plane `_observe`
Retry observe_dom của r3 không còn giá trị (mismatch do session.state cũ, đọc lại không chữa) và sẽ chặn đường chữa mới của worker, nên REVERT hoàn toàn: bỏ `OFF_ORIGIN_RETRY_SECONDS`, nhánh off-origin, field `AgentRun.allowed_origins`, import `origin_allowed`. `_observe` trở lại đúng bản gốc (phát `wait` refresh), thêm 1 dòng comment. Không đổi import so với trước r3 nên không cần `hgraph sync`.
- FakeWorker (`tests/test_vision_agent_loop.py`) áp luật worker MỚI: off-origin chỉ cho `close_popup`/`back` và refresh (setup wait + refresh_observation); giữ cải tiến r3 (rule fail trả operation `rejected` có `outcome_code`) và `errors_after_click`.
- Test thay: (a) off-origin stale read -> đúng 1 refresh wait, kết thúc `agent_done`, không `origin_blocked`; (b) không bao giờ settle -> `state_mismatch`, 1+3 lần observe, 2 refresh; (c) off-origin chỉ prepare được duy nhất `wait`+refresh, click/type/wait thường bị skip `origin_blocked`; (d) trong origin vẫn refresh (giữ). Test cũ refresh giữ nguyên.
- Lưu ý trung thực: vì source control-plane về bản gốc, các test này xanh cả trên source gốc khi fake dùng luật mới (chúng là chặn hồi quy). Phần "đỏ trên code cũ" ở r3 đã chứng minh ở lượt trước (3 failed với luật worker cũ) và worker spec trên là test đỏ->xanh thật cho r4.

## 4. Docs
- docs/vision-agent-operations.md (mục Safety/K3, ~dòng 558-562): thay 3 dòng retry bằng mô tả ngoại lệ refresh đọc-chỉ + kết thúc `state_mismatch` nếu 3 lần vẫn lỗi.
- docs/adr/038-vision-agent-loop-engine.md (K3): thêm 1 đoạn về ngoại lệ refresh.

## 5. Kiểm chứng
```
uv run ruff check .                                              -> All checks passed!
uv run pytest tests/test_vision_agent_loop.py tests/test_vision_agent_loop_qa.py -> 192 passed
uv run pytest tests/test_vision_live_persistence.py              -> 27 passed
npm run typecheck (workers/playwright)                           -> sạch
playwright 3 spec file                                           -> 141 passed
```
Postgres cô lập `r4-vision-fixture-pg` (127.0.0.1:55437) tôi tự mở, đã `docker stop` (--rm); xác nhận 0 container r3/r4 còn lại. Stack compose không đụng, không rebuild. Cần rebuild playwright-worker (đổi TS) + control-plane/temporal-worker không đổi code so với trước r3 nhưng phiên chính vẫn cần rebuild worker trước phiên live kế tiếp.

git diff --stat (nhiều file vẫn untracked nên git không hiện diff; liệt kê trạng thái):
```
 M workers/playwright/src/vision-operations.ts   | 102 +++-- (file đã có thay đổi chưa commit từ trước; phần tôi sửa ~4 dòng, line 521-529)
 M docs/vision-agent-operations.md               | +61 (phần tôi: ~5 dòng)
?? apps/control-plane/application/vision_agent_loop.py   (untracked; thay đổi cuối cùng của tôi chỉ 1 dòng comment so với bản gốc)
?? tests/test_vision_agent_loop.py                       (untracked; FakeWorker + 4 test)
?? workers/playwright/src/vision-agent-mode.spec.ts      (untracked; +1 test)
?? docs/adr/038-vision-agent-loop-engine.md              (untracked; +1 đoạn K3)
```

GRAPH_UPDATE
- graph đã cập nhật: không cần — không thêm/xoá file, không đổi quan hệ import
- file mới đã đưa vào graph: không có
- hgraph check --changed: exit 1; 30 file `uncovered-changed` liệt kê, đều là nợ cũ (codex_service.py, vision.py, config.py, dashboard...). Không có dòng nào nhắc vision_agent_loop.py, tests/test_vision_agent_loop.py, vision-operations.ts, vision-agent-mode.spec.ts, docs sửa ở lượt này.
