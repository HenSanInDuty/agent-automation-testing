---
phase: 02
title: Chữ trên trang trong observation — contract và worker
status: pending
owner: both
qa: required
dependencies: [phase-01]
---

# Phase 02 — Chữ trên trang: contract + worker

## Mục tiêu

Worker thu **chữ nhìn thấy trên trang** (role `alert`/`status`, heading, đoạn văn ngắn) và trả về trong
`CodexDomObservation`, để agent thấy thông báo lỗi, tiêu đề, bộ đếm mà không phải xin ảnh chụp (hiện prompt
`agent-loop-v3` buộc xin ảnh, tốn thêm lượt gọi model; case lỗi gốc: `login-failure` bị `not_achieved` sai vì
snapshot không có chữ).

Phase này chỉ làm phía **contract + worker** (đầu ra của worker, chưa ai dùng). Phần control plane render chữ vào
snapshot và đổi prompt là phase 03. Tách vậy vì phase này đổi contract chung và sinh lại file TS, nhiều file, cần
QA riêng trước khi Python phụ thuộc vào nó.

Ràng buộc từ plan.md/ADR-046:
- Capability mới (đề xuất tên `page-text-v1`) trong danh sách capability worker; **chỉ bật khi `agent_mode`** và
  control plane yêu cầu trong `required_capabilities`; planner v4 không yêu cầu nên không đổi hành vi.
- Trường mới là **tuỳ chọn** trong `CodexDomObservation`, mặc định rỗng và **bị bỏ khỏi serialization khi rỗng**
  để không đổi hash/byte của observation planner v4 (`codex-dom-v11`, schema hash không đổi).
- Có giới hạn: số mục, độ dài mỗi mục, tổng byte (observation đã có trần 65 536 byte, `canonical_bytes`).
- Chữ đi qua bộ lọc nhạy cảm giống tên element (`validate_locator_value` / redaction), mục không qua lọc thì bị
  bỏ và đếm, không làm hỏng cả observation.

## Tiêu chí xong (kiểm chứng được)

1. `CodexDomObservation` có trường chữ tuỳ chọn; một observation **không có** chữ serialize ra đúng byte như
   trước (test so sánh với fixture cũ trong `packages/contracts/fixtures/vision-worker-v4/`; hash planner không đổi,
   `tests/test_codex_bridge_contracts.py` và `tests/test_vision_dom_transport.py` qua không sửa expected cũ).
2. `uv run python packages/contracts/export_vision_worker.py` đã chạy; `--check` trả 0;
   `uv run pytest tests/test_vision_worker_contracts.py -q` qua (so `vision-contract.generated.ts` với bản render).
   `vision-contract.generated.ts` không sửa tay.
3. Worker khai capability mới trong kết quả `open`, và chỉ thu chữ khi `agent_mode === true` **và**
   `required_capabilities` có capability đó. Có spec chứng minh: không có capability thì observation không có
   trường chữ.
4. Spec worker (Playwright) trên trang fixture chứng minh: thu được alert/status/heading/đoạn ngắn nhìn thấy;
   bỏ qua phần tử ẩn (`display:none`, `aria-hidden`), nội dung trong `script/style`, và nội dung `<input>`
   (không bao giờ thu giá trị ô nhập, kể cả ô mật khẩu); chữ quá dài bị cắt; vượt số mục thì đặt cờ cắt.
5. Spec chứng minh chữ chứa thứ nhạy cảm (e-mail dạng mẫu, chuỗi giống token/`password=...`) bị lọc trước khi
   rời worker, kể cả khi `owned-test-target-v1` bật (cờ FE test không nới lọc chữ trang; xem rủi ro).
6. `cd workers/playwright && npm.cmd run typecheck && npx.cmd playwright test src/vision-dom.spec.ts src/vision-agent-mode.spec.ts`
   qua (dùng một từ cho `-g` nếu cần, xem plan.md "Lưu ý dễ vấp"); `uv run ruff check .` sạch.
7. `python .pytest-artifacts/refresh_manifest.py` đã chạy sau khi sửa source và `tests/test_codex_bridge_benchmark.py`
   qua.
8. ADR-046 có mục bổ sung (cùng phong cách mục 5/6) ghi capability, giới hạn, bộ lọc.

## File liên quan (phạm vi được đụng; ngoài đó cấm)

Contract (Python, nguồn sự thật):
- `packages/contracts/src/auto_at/contracts/codex_bridge.py` (`CodexDomObservation`, dòng ~125; thêm trường + tăng
  cơ chế bỏ khỏi serialization khi rỗng)
- `packages/contracts/src/auto_at/contracts/vision_worker.py` (`required_capabilities` Literal, dòng ~43)
- `packages/contracts/export_vision_worker.py` (chỉ chạy; sửa nếu cần đăng ký model, không đổi khác)
- `packages/contracts/fixtures/vision-worker-v4/` (thêm fixture có chữ; không sửa fixture cũ)

Worker (TS):
- `workers/playwright/src/vision-contract.generated.ts` (**chỉ sinh bằng exporter**)
- `workers/playwright/src/vision-dom.ts` (thu chữ)
- `workers/playwright/src/vision-operations.ts` (capability trong `open`, ~dòng 141–235; truyền cờ thu chữ)
- `workers/playwright/src/vision-dom.spec.ts`, `workers/playwright/src/vision-agent-mode.spec.ts`,
  `workers/playwright/src/fixtures/agent-loop-target.ts` (fixture trang có alert/heading)

Test Python:
- `tests/test_vision_worker_contracts.py`, `tests/test_codex_bridge_contracts.py`, `tests/test_vision_dom_transport.py`

Tài liệu / chuẩn / graph:
- `docs/adr/046-agent-loop-task-testing.md` (thêm mục)
- `benchmark/vision/codex/manifest.json` (chỉ qua `refresh_manifest.py`)
- Convention: `AGENTS.md` — "Shared runner and agent contracts belong in `packages/contracts/`", "Add focused tests with
  each behavior change"; giữ contract `TestExecutionRequest`/`TestExecutionResult` (không đụng).
- Graph phải đọc trước: `docs/graphs/playwright-vision-worker.md`, `docs/graphs/codex-bridge.md`. Graph cập nhật
  sau: `playwright-vision-worker` (chạy `hgraph sync`/`hgraph add` theo tooling hiện có). Không lập graph mới.
  Chạy `hgraph impact` cho `vision-dom.ts` và `codex_bridge.py` trước khi bắt đầu để xác nhận blast radius.

Dự kiến ~10 file chạm; nếu dev thấy cần sửa file ngoài danh sách này (đặc biệt phía control plane), dừng và hỏi
PM, không tự mở rộng.

## Không làm

- Không sửa `render_snapshot`, prompt, `vision_agent_loop.py` (phase 03).
- Không đổi planner v4: không thêm capability vào mặc định, không đổi `codex-dom-v11`, không đổi
  `codex_exploration.py`.
- Không thu giá trị `<input>`/`<textarea>`, nội dung `contenteditable` đang gõ, `title`/`alt` ẩn, hay chữ trong
  iframe/shadow đóng.
- Không nới danh sách từ nhạy cảm, không bỏ từ `password` khỏi danh sách (xem rủi ro).
- Không đổi `step_deadline`/guard runtime.

## Rủi ro / việc cần user duyệt

- **Dữ liệu chữ trang đi tới model provider**: trước giờ chỉ tên element (≤120 ký tự, đã lọc) đi qua. Chữ đoạn
  văn có thể chứa dữ liệu cá nhân của FE thật (phase 05). AGENTS.md yêu cầu xác định phân loại dữ liệu và redaction
  trước khi làm việc LLM. Đề xuất giữ: chỉ ở agent mode, bộ lọc nhạy cảm, trần byte; tenant đã đồng ý chuyển DOM
  (ADR-046). Nếu user muốn nới/siết (vd chỉ alert/status/heading, không đoạn văn) thì quyết định trước khi code.
- **Quyết định chờ user "Nhãn tiếng Anh Password"** (plan.md) ảnh hưởng gián tiếp: chữ trang chứa "Password" (nhãn,
  tiêu đề "Reset password") sẽ bị lọc theo quy tắc hiện tại và biến mất khỏi snapshot, làm giảm lợi ích của phase.
  Không tự đổi policy redaction; ghi lại số mục bị lọc để phase 04 đo ảnh hưởng.
- Đổi contract chung: `vision-contract.generated.ts` phải khớp bản sinh, nếu lệch thì `test_vision_worker_contracts`
  đỏ. Tách phase này khỏi phase 03 để phía Python chưa phụ thuộc vào nó.
- Quyết định "dung sai `step_deadline`" **không** thuộc phase này; test worker trên host Windows có thể dao động
  (`invalid_step_deadline`), A/B với HEAD trước khi coi là hồi quy.
