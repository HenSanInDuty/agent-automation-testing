---
phase: 6
title: "End-to-end + benchmark + docs"
status: pending
priority: P1
owner: be-developer
qa: required
dependencies: [2, 3, 4, 5]
---
## Mục tiêu
Chứng minh engine chạy thật: task click-hết-control mongchiton trên `agent_loop`, collect + evaluate bằng benchmark độc lập
(metrics/oracle không đổi), so sánh với round 21; ghi quyết định (ADR-038) và tài liệu vận hành; hồi quy toàn bộ.

## Database Impact
Không đổi schema. Chạy migration phase 1 trên stack local (`uv run alembic upgrade head`) trước khi deploy.

## File liên quan
Tạo:
- `docs/adr/038-vision-agent-loop-engine.md`
- `benchmark/vision/accuracy/AGENT-LOOP-01-<date>.md` (báo cáo vòng)
Sửa:
- `docs/vision-agent-operations.md` (mục agent loop: bật cờ, chọn engine, mã lỗi, giới hạn 20 lần gọi, allowlist observe-only)
- `plan/09112026103202-vision-accuracy-loop/README.md` (handoff ngắn trỏ tới báo cáo vòng)
Không sửa `benchmark/vision/accuracy/run.py`: session agent loop được tạo bằng helper chạy vòng local (`.pytest-artifacts/`, không track)
gọi `POST /explorations` với `engine=agent_loop`, rồi `run.py import`/`resume`/`collect`/`evaluate` như các vòng trước. Báo cáo vòng
theo quy ước benchmark (mỗi vòng một `*.md` trong `benchmark/vision/accuracy/`); ADR chỉ ghi quyết định, không chép số liệu.

## Luồng dữ liệu của phase này
Deploy control-plane/temporal-worker/playwright-worker/dashboard → bật `VISION_AGENT_LOOP_ENABLED` → helper local tạo session
(`engine=agent_loop`, cùng target/task, cùng provider/policy round 21, `max_steps=20`) → `run.py import` với oracle `9242b33d…` → watcher
→ `run.py collect` → review outcome độc lập (cùng quy trình round 21) → `evaluate`.

## Convention áp dụng
`AGENTS.md` "Boundaries requiring user direction" (chạy live gọi model = chi phí → xin phép trước) và "Assistant token budget and round handoff"
(một vòng benchmark mỗi phiên, handoff trong plan README). Benchmark README: reviews content-addressed, không relabel, không retry click.

## Graph liên quan
Sau phase: `hgraph check --changed` cho toàn plan; đảm bảo graph `vision-agent-loop` / `playwright-vision-worker` khớp source.

## Các bước thực hiện
1. Hồi quy toàn bộ: `uv run ruff check .`, `uv run pytest` (chia nhóm), worker spec v4 + agent, dashboard test/typecheck/lint. So với baseline phase 0.
2. Xin user cho phép chạy live (chi phí model, token Claude bridge còn hạn — chạy lại `scripts/export_claude_bridge_token.py` nếu hết).
3. Deploy + kiểm checksum source trong container (mẫu `.pytest-artifacts/accuracy_round.py start`).
4. Chạy session agent loop với task click-hết-control; theo dõi bằng `scripts/watch_vision_session.py`.
5. `collect`, review outcome độc lập (frame, checkpoint page_url, redirect review, download evidence), `evaluate` → `score.json`.
6. Báo cáo vòng: C/A, detection (ghi rõ không so được trực tiếp với v4 vì không có inventory toàn trang), số lần gọi model,
   token, thời gian, số action bị chặn theo mã, terminal reason; so sánh bảng với round 16/19/20/21.
7. ADR-038 (quyết định, phương án loại, nợ kỹ thuật lặp primitive, K1–K5) + docs vận hành.
8. Nếu 20 lần gọi không đủ phủ task: ghi số liệu và đề xuất plan nâng trần (không làm trong plan này).

## Unit test phải viết
Không thêm unit test mới (không sửa `run.py`).

## Tiêu chí xong (checklist)
- [ ] Hồi quy toàn bộ xanh hoặc chỉ đỏ đúng các test đã đỏ ở baseline phase 0 (AC7).
- [ ] Session agent loop terminal với reason ∈ {agent_done, agent_stopped, agent_step_limit, session_timeout}; `run.py collect` +
      `evaluate` thoát 0; `score.json` có trong thư mục run; 0 target oracle bị `sensitive_action_blocked` (AC6).
- [ ] `git diff --exit-code -- benchmark/vision/accuracy/metrics.py benchmark/vision/accuracy/oracle-mongchiton-1280-v1.json` thoát 0.
- [ ] Nếu phase 3 chưa kiểm bridge thật: job agent thật đã parse thành công trong session này (ghi job id).
- [ ] Báo cáo vòng + ADR-038 + docs vận hành cập nhật.

## Rủi ro & tín hiệu nhận biết hỏng
- 20 lần gọi không đủ: coverage thấp do mỗi popup dừng batch → ghi số liệu, không nâng trần trong plan này.
- Bridge ~41 s/job → session ~15 phút; `max_session_seconds` phải đủ.
- Từ khoá nhạy cảm chặn nhầm target oracle → thấy `sensitive_action_blocked` trên mct-xx trong trace.
- Detection gate dựa trên inventory → có thể "fail" theo định nghĩa v4; báo cáo nêu rõ, không đổi metrics.
