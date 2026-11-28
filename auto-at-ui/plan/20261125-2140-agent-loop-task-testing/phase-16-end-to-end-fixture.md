---
phase: 16
title: End-to-end trên fixture task-ui — từ assessment tới verdict thật
status: completed
owner: both
qa: required
dependencies: [phase-15, phase-15b, phase-15c]
---

# Phase 16 — End-to-end trên fixture (ADR-047, phase B9)

## Mục tiêu

Chứng minh cả chuỗi hoạt động và an toàn trên FE cục bộ `benchmarks/targets/task-ui`: phiên agent-loop `achieved` → yêu cầu draft
(người A, nhập giá trị) → người B khác, vai `reviewer`/`project_admin`/`tenant_admin`, duyệt → preflight → test case + một run
deterministic → `TestExecutionResult.status` là verdict. Đo độ ổn định của **test sinh ra** (chạy lại N lần), không chỉ của phiên.
Chạy các ca âm để chứng minh test không "pass nhầm" và các rào chắn của phase 13-14 hoạt động trên stack thật.

## Tiêu chí xong (kiểm chứng được)

1. Với ba task `login-success`, `todo-add`, `search-results` (`benchmarks/task-ui/tasks.v1.json`): từ phiên `achieved` (có ứng
   viên assertion, phase 10) sinh draft, người B duyệt, run `passed`. Ghi ID phiên/draft/run, source (giá trị test che trong báo cáo
   nhưng có trong DB theo thiết kế), số lượt gọi model của phiên.
2. Tính xác định: mỗi test đã duyệt chạy lại ít nhất 5 lần trên fixture sau `POST /__reset` (ghi chú trong `tasks.v1.json`):
   `passed` ≥ 90% (cùng ngưỡng của `benchmark/task_ui/stability.py:23`), ghi số chạy lại.
3. Ca âm (mỗi ca có bằng chứng, đúng kết quả mong đợi): (a) trang `/broken` (task `broken-save`/`broken-counter` kỳ vọng
   `not_achieved`) → không sinh draft (`assessment_not_achieved`, Q9); (b) fixture bị phá cố ý sau khi duyệt (đổi chữ kết quả) → run
   `failed` (test không pass nhầm); (c) phiên không nhất quán (đồng thuận < ngưỡng) → `assessment_inconsistent`; (d) cùng người
   yêu cầu và duyệt → từ chối; (e) contributor duyệt → từ chối; (f) thiếu xác nhận tài khoản dùng một lần → từ chối; (g) project
   không bật cờ + bước `type` → `input_value_not_allowed`; (h) bằng chứng hết hạn → `evidence_expired`; (i) ô có nhãn "Password"
   (Q4) → phiên `blocked` ở agent, nên trên stack thật kết quả đúng là `assessment_not_achieved` (user chấp nhận 2026-11-28,
   phase 15c); `locator_unavailable` cho locator `redacted` chỉ chứng minh ở ca DB; (j) `revised-draft` và sửa preflight cho test có giá trị → `credentials_in_source`.
4. Quét nơi lưu giá trị trên DB thật của stack: giá trị mẫu chỉ ở tập nơi đã khai báo (draft, test case, `test_runs.request`,
   `outbox_events.payload`, phản hồi API; workflow history và artifact theo phase 07), vắng ở DB phiên, `visual_agent_steps`,
   `audit_events`, `generation_requests`, log control plane/worker. Báo cáo ghi từng bảng đã quét và lệnh `SELECT` đọc.
   **Quét artifact thật (nơi 9, Q11):** với run của test đã duyệt, tải trace zip và screenshot về thư mục tạm (không commit),
   giải nén trace rồi tìm giá trị mẫu (`grep -rlaF`) trong `*.trace`, `resources/src@*.txt`, và kiểm screenshot bằng mắt hoặc
   so khớp ô; ghi file nào chứa. Kỳ vọng theo spike phase 07 (`reports/phase-07/runner-r1.md` mục 3): có trong trace và snapshot
   DOM kể cả khi run pass; khi trang gửi request thì còn có trong `0-trace.network` và `resources/<sha1>.dat` (ADR-047 nơi 9, cập nhật phase 15c); `0-trace.stacks` không có. Nếu xuất hiện ở loại artifact khác (log, `playwright-output`
   khi pass, nơi nào ngoài tập khai báo) thì ESCALATE. Test tự động (tiêu chí 7) ghim danh sách nơi khai báo để thêm một nơi mới làm
   test fail (AC3).
4b. Ca e2e kiểm form (phase 15b): với phiên `login-success`/`todo-add` có bước `type`, màn dashboard (hoặc `GET .../test-draft/inputs`)
   hiện độ dài mong đợi bằng độ dài giá trị mà người A nhập thành công; project không bật cờ → không có độ dài.
5. Hai actor thật trong tenant local (header `X-Actor-Id` khác nhau, vai khác nhau; xem "Cách chạy" của plan.md về header local).
6. Báo cáo chạy ghi: HEAD, prompt `agent-loop-v4`, model, số phiên, tỉ lệ `achieved` có ứng viên, tỉ lệ draft tạo được, tỉ lệ run passed,
   lỗi nào chưa giải thích. Không kết luận ngoài fixture đơn giản (phase 05 là FE thật).
7. Suite test tự động mới cho chuỗi (dùng stack giả/fixture DB, không gọi model thật) qua trong CI cục bộ: `uv run ruff check .`,
   các test của phase 08-14, `cd apps/dashboard && npm run typecheck && npm test`. Bộ test Python đầy đủ không bắt buộc chạy trọn
   (mất hơn 40 phút trên máy này); ghi nhóm test đã chạy.
8. `hgraph check --changed` sạch; graph `agent-task-draft` hoàn chỉnh (mọi file mới của phase 08-16 có mặt), cập nhật `task-ui-stability`,
   `vision-agent-loop`.

## File liên quan (phạm vi được đụng; ngoài đó cấm)

- Mới: `tests/test_agent_task_draft_e2e.py` (chuỗi với DB fixture, không model thật), `scripts/run_agent_task_draft_e2e.py`
  (kịch bản trên stack thật, nối vào mẫu `scripts/run_task_stability.py`), báo cáo trong `reports/phase-16/`.
- Sửa (tối thiểu, nếu cần): `benchmark/task_ui/stability.py` (thêm đo độ ổn định của test đã duyệt, không đổi công thức hiện có;
  `tests/test_task_stability.py` cập nhật tương ứng), `benchmarks/task-ui/tasks.v1.json` (chỉ thêm trường nếu cần, giữ tương thích).
- Đọc/dùng: `benchmarks/targets/task-ui/server.mjs` (không sửa trừ khi ca âm (b) cần chế độ phá cố ý có sẵn: ưu tiên dùng `/broken`
  và `POST /__reset`), `scripts/run_task_stability.py`, `docker-compose.agent-loop.yml`, các use case/route của phase 08-14.
- Chạy cần: stack theo "Cách chạy" của plan.md (4 file compose + `--profile claude`), token bridge còn hạn, container postgres
  `agent-task-fixture-postgres` cho test DB.
- Convention: `AGENTS.md` — thay đổi hành vi kèm test, `uv` cho Python, không `.env*`/token trong repo. Graph phải đọc:
  `docs/graphs/task-ui-stability.md`, `docs/graphs/vision-agent-loop.md`, `docs/graphs/agent-task-draft.md`; cập nhật: cả ba.
- Tham chiếu: `docs/adr/047-assessment-to-playwright-draft.md` (AC1-AC7), `docs/adr/046-agent-loop-task-testing.md`.

## Không làm

- Không chạy trên FE thật của người dùng (phase 05); không đổi code sản phẩm của phase 08-15 (lỗi phát hiện thì báo, phiên chính
  quyết định phase nào sửa).
- Không đổi chính sách redaction (Q4, Q5), không thêm tính năng; không `docker compose down -v` làm mất dữ liệu người dùng.
- Không tự duyệt thay người dùng ngoài hai actor thử nghiệm của fixture.

## Rủi ro / việc cần user duyệt

- Mỗi phiên gọi model thật (25-61 giây, ~2-3 lượt/phiên): ước lượng thời gian; chia nhóm lệnh ≤ 9 phút.
- Fixture đơn giản: kết quả ổn định không suy ra cho FE thật; ghi rõ trong báo cáo.
- Dữ liệu fixture đổi mỗi lần chạy (thêm/xoá việc): bắt buộc `POST /__reset` trước mỗi lần chạy lại test; nếu test sinh ra không tự reset,
  ghi là điều kiện tiên quyết của người dùng cho FE thật (ADR-047, mục Rủi ro).
- Việc cần user duyệt: không; nếu tỉ lệ pass < 90% hoặc phát hiện nơi lưu giá trị ngoài danh sách, ESCALATE.
