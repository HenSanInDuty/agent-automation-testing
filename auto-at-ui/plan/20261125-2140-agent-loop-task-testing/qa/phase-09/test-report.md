# Phase 09 QA report

QA VERDICT: PASS

Môi trường: Windows 11, `uv run`, Postgres fixture 127.0.0.1:55437, `CODEX_BRIDGE_ENABLED=false`.

## Output thật

```
CODEX_BRIDGE_ENABLED=false uv run pytest tests/test_agent_task_consistency.py tests/test_qa_p09_agent_task_consistency.py tests/test_vision_routes.py tests/test_vision_results.py tests/test_agent_task_trace.py tests/test_qa_p08_agent_task_trace.py -q -rs --basetemp=.pytest-artifacts/tmp-p09-qa -p no:cacheprovider
275 passed, 1 xfailed, 3 warnings in 79.64s     (0 dòng SKIPPED)
uv run ruff check .   -> All checks passed!
hgraph add agent-task-draft tests/test_qa_p09_agent_task_consistency.py -> Đã thêm 1 file (tổng 14)
hgraph check -> 8 graph, 538 file source ✔ Không có vấn đề. (exit 0)
```

`hgraph check --changed` vẫn exit 1 với `uncovered-changed`: toàn bộ là dương tính giả đã biết (file tracked chưa commit, tiền tố `auto-at-ui/`), gồm cả 3 file phase 09 sửa (routes/vision.py, config.py, repositories.py) vốn đã trong graph vision-exploration; 2 file mới của phase 09 và file QA không bị báo. Không có drift/stale-file. Sẽ sạch sau khi commit.

Skip: 0. Test phase 09 (dev + QA) chạy thật trên Postgres fixture.

## Phủ tiêu chí

1 (route, READ, 404 không lộ): PASS. Body và header (trừ id theo request) của "không tồn tại" giống hệt với: không grant, project khác, tenant khác, service, session tenant khác; `Cache-Control: private, no-store`.
2 (mẫu số): PASS. unavailable/running/cancelled/failed/không assessment/status lạ/assessment sai kiểu không vào mẫu số; cách ly tenant/project/url/intent/engine đúng.
3 (ngưỡng qua config): PASS. env -> Settings, mặc định 0,9; 0, âm, >1, nan/inf, chuỗi bị từ chối lúc dựng Settings; đổi ngưỡng đổi `eligible`; chỉ config.py đọc env.
4 (reason): PASS. Từng reason, tổ hợp 3 reason đúng thứ tự, 1 phiên (100% + small_sample). Biên 9/10 ở 0,9 là eligible, khớp `>=` của stability.py:187.
5 (không đa số thắng ngầm): PASS. 4+1 trả đủ 4 khoá, eligible=false; hoà 2-2 xác định (chữ cái, khớp stability.py:138).
6 (không migration, chỉ đọc): PASS. Hàng/`updated_at`/`state`/`task_assessment` không đổi; không tạo phiên; không ghi. Index: truy vấn lọc `tenant_id`, `project_id` (có index) rồi `target_url`, `intent_hash`; không cần index ở quy mô hiện tại, đo lại nếu một project có hàng chục nghìn phiên.
7 (test, ruff, hồi quy, graph): PASS (xem trên). Đối chiếu số với `stability._task_stats` trên 40 phân bố ngẫu nhiên: khớp.

Stress test: không cần. Truy vấn là một SELECT theo khóa đã lọc, không vòng lặp trên tập lớn, không job hàng loạt, không đổi transaction/lock; đã thử nhóm 150 phiên.

## Lưu ý không chặn

L1. `apps/control-plane/application/agent_task_consistency.py:80`: `item.task_assessment.get("status") in ASSESSMENT_STATUSES` (frozenset) ném TypeError khi `status` không hashable (vd list) -> HTTP 500. Tái hiện: test `test_denominator_ignores_unassessed_or_unfinished_sessions[kind11]` (xfail strict; khi sửa, test sẽ XPASS-fail để nhắc bỏ marker). Dữ liệu này không thể xuất hiện qua đường ghi hiện tại (assessment do validator của nền tảng ghi), nên không vi phạm tiêu chí; gợi ý sửa: `isinstance(status, str) and status in ...`.
L2. Agreement được `round(…, 4)` trước khi so ngưỡng (giống stability.py); chỉ lệch ở nhóm hàng chục nghìn phiên, bỏ qua.

## Chưa test được

- Stack đang chạy ở http://localhost:7000: `/openapi.json` chỉ có `/trace`, không có `/consistency` (container build từ code cũ). Không gọi endpoint trên phiên thật, không rebuild/restart theo yêu cầu. Cần rebuild control plane để kiểm trên phiên thật. Không tính FAIL.
- Không gọi mongchiton.vn hay localhost:1000.
