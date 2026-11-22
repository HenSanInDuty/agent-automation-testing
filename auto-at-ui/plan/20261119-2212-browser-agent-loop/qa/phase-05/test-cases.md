# Phase 5 (Dashboard) - Test cases

Runner: unit = `node --experimental-strip-types --test` (apps/dashboard); e2e = Playwright `workers/playwright/src/vision-dashboard.spec.ts --workers=1` (API mock, dashboard built, port 3107).

| ID | Nhóm | Case | Mong đợi | Automation | Kết quả |
|---|---|---|---|---|---|
| P5-01 | Happy | `agent_loop_enabled` false/vắng -> không có `#vision-engine` | select không tồn tại | e2e "Agent loop engine is offered only when enabled..." | PASS |
| P5-02 | Happy | `agent_loop_enabled` true -> select, mặc định Planner | `#vision-engine` value `planner` | cùng e2e | PASS |
| P5-03 | Happy | Submit khi để Planner | payload KHÔNG có key `engine` | cùng e2e + unit `engineRequestFields` | PASS |
| P5-04 | Happy | Chọn Agent loop, submit | payload đúng `{..., engine:"agent_loop"}`, hint đổi sang "Agent loop: ..." | cùng e2e | PASS |
| P5-05 | Happy | Ledger session agent, op 2 có `agent_step` | block `Agent step` có 3 trường (Đánh giá bước trước / Memory / Mục tiêu kế) + dòng Blocked `click: The page changed ...` | e2e "agent step shows reasoning..." | PASS |
| P5-06 | Hồi quy | Session planner (không `agent_step`) | không có block `Agent step`, ledger vẫn chọn được op 2 (aria-current) | cùng e2e | PASS |
| P5-07 | Happy | 10 mã mới (stale_ref, origin_blocked, sensitive_action_blocked, agent_step_limit, agent_done, agent_stopped + invalid_ref, action_kind_blocked, ineligible_target, batch_stopped) | mỗi mã một câu riêng, không rơi vào thông báo chung | unit "agent-loop reason codes map..." | PASS |
| P5-08 | Biên | Mã lạ / rỗng / undefined / `__proto__` / 500 ký tự | câu fallback có giới hạn 80 ký tự, không throw | unit "unknown or hostile skipped reasons..." | PASS |
| P5-09 | Biên | `agent_step` vắng/null/`{}` | null / "Not recorded" x3 | unit "agent step view is absent..." | PASS |
| P5-10 | Biên | next_goal 2000 ký tự; tiếng Việt có dấu; kind 200 ký tự | cắt 600 + "…"; giữ nguyên dấu; kind cắt 40 | unit (cùng) | PASS |
| P5-11 | Biên | engine lạ (`constructor`, undefined) | coi như planner, không thêm field | unit "engine values..." | PASS |
| P5-12 | Biên | `skipped_actions` không phải mảng, phần tử null, kind/reason sai kiểu, 50 phần tử | không throw, tối đa 20 dòng, fallback "Action: Skipped before..." | unit "QA: agent step view tolerates malformed..." (QA thêm) | PASS |
| P5-13 | Biên | Viewport 400px, memory chuỗi 720 ký tự không khoảng trắng | `scrollWidth <= innerWidth` | e2e "agent step text wraps at phone width..." | PASS |
| P5-14 | Lỗi | Policy không có field `agent_loop_enabled` (BE cũ) | ẩn select, payload planner | P5-01 | PASS |
| P5-15 | Hồi quy | Gating `trace_version === "v4"` không đổi (session agent vẫn v4, legacy fixture) | các e2e legacy/v4 sẵn có xanh | 55/57 e2e sẵn có+mới | PASS |
| P5-16 | Hồi quy | typecheck / lint dashboard | exit 0 | tsc, eslint | PASS |
| P5-17 | Hồi quy | e2e "Vision cards align on desktop..." (spec:238) | xanh | e2e | FAIL, nhưng ĐỎ Ở BASELINE HEAD (sẵn có) - không tính cho phase |
| P5-18 | Hồi quy | e2e "a saved session focuses the website..." (spec:336) | xanh | e2e | FAIL, nhưng ĐỎ Ở BASELINE HEAD (sẵn có) - không tính cho phase |

Không áp dụng: test tái hiện bug (phase là feature, không phải fix). Stress test: không cần - thay đổi chỉ render UI, không vòng lặp tập lớn/query/job; danh sách blocked đã chặn 20 dòng.
