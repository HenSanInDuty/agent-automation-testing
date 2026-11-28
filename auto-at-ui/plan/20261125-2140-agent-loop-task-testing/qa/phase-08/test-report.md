# Phase 08 — test report (QA)

QA VERDICT: FAIL

Môi trường: Windows, `uv run`, Python 3.12, `CODEX_BRIDGE_ENABLED=false`; Postgres fixture `127.0.0.1:55437` (test DB chạy thật, 0 skip); DB cục bộ `127.0.0.1:5432` chỉ đọc (`SET TRANSACTION READ ONLY`, không ghi).

## Phán quyết
FAIL một tiêu chí: AC4 ("không chứa ref `version:n`"). Ref agent `1:7` do model viết trong `task_assessment.summary`/`checks[].evidence` được chép nguyên vào gói vết. Đã xảy ra thật: phiên cục bộ `e660f6a3-9de6-4228-a98a-b620f8fc78ff` có summary "nhập vào 1:7 và 1:8, rồi nhấn 1:9" nằm trong gói vết (1/169 gói dựng được). Test tái hiện: `test_p08_agent_ref_written_in_the_assessment_summary_does_not_reach_the_trace` (xfail strict; đổi thành pass khi sửa). Nguồn: `packages/contracts/src/auto_at/contracts/agent_task_trace.py:71-81` (`AgentTaskAssessmentCopy` chép `summary`, `checks`) và `domain/agent_task_trace.py:57-68`. Hướng sửa: bỏ/che mẫu ref trong bản sao assessment, hoặc đổi AC4 thành chỉ áp dụng cho `steps` (nhờ PM/leader quyết).

Cùng nguồn, giá trị gõ: nếu model viết giá trị đã gõ vào summary/evidence thì nó nằm nguyên trong gói vết (test `test_p08_FINDING_...` khẳng định đếm được 2 lần). Developer đã nêu; redaction theo mẫu không biết giá trị tài khoản test. Có rò, ngoài `steps` (steps sạch hoàn toàn).

Finding nhẹ (không chặn): `domain/agent_task_trace.py:130` `UUID(str(item))` ném `ValueError` thô khi `operation_ids` hỏng, không phải `AgentTaskTraceRefused`; tương tự `target_url` > 2000 ký tự ném `ValidationError` thô. Dữ liệu thật do vòng lặp ghi nên khó xảy ra. Test: `test_p08_non_uuid_operation_id_...` (xfail strict).

## Kết quả (output thật)
```
$ CODEX_BRIDGE_ENABLED=false uv run pytest tests/test_agent_task_trace.py tests/test_qa_p08_agent_task_trace.py tests/test_vision_handoff.py tests/test_vision_agent_task_assessment.py tests/test_vision_results.py -q -rs --basetemp=.pytest-artifacts/tmp-p08-qa -p no:cacheprovider
148 passed, 2 xfailed, 3 warnings in 50.37s          (0 skipped)

$ uv run ruff check .
All checks passed!

$ hgraph add agent-task-draft tests/test_qa_p08_agent_task_trace.py
Đã thêm 1 file vào docs/graphs/agent-task-draft.md (tổng 11).
$ hgraph check
✔ Không có vấn đề.
$ hgraph check --changed
✖ [uncovered-changed] ... 16 file tracked chưa commit, tiền tố `auto-at-ui/` (agent_loop.py, vision_agent_loop.py, codex_bridge.py, vision_worker.py, test cũ ...)
```
`--changed`: không file phase 08 nào trong danh sách; đây là dương tính giả đã biết (file tracked chưa commit, đường dẫn có tiền tố), cùng danh sách developer đã báo.

Đã test: 48 case QA + 40 case developer; 46 pass / 2 xfail (finding). Skip: 0.

## Replay DB cục bộ (chỉ đọc)
Script scratch ngoài repo: `.../scratchpad/qa_replay.py`.
```
{'unavailable refused assessment_unavailable': 45, 'completed built': 169, 'completed refused operation_failed': 3}
violations: 1 [('e660f6a3-...', 'ref-like', ['nhập vào 1:7 và 1:8, rồi nhấn 1:9"'])]
```
Kiểm cho 169 gói: hash ổn định qua hai lần đọc, hash kiểm lại sau round-trip JSON, không key cấm (`text/ref/x/y/bounding_box/executed_click`), số step = số operation explore, mọi `type` có `text_chars`. Chỉ vi phạm là ref trong summary ở trên.

## Chưa test được
- Stress test: không cần, hàm thuần trên một phiên, không vòng lặp tập lớn/query/transaction/lock mới.
- Giá trị gõ thật trong DB cục bộ: không thể quét (text không được lưu); chỉ quét key và mẫu ref.
- RBAC: ngoài phạm vi phase (caller phase 14).
- DB production: không có.

Tài liệu: `qa/phase-08/test-cases.md`, file này, automation `tests/test_qa_p08_agent_task_trace.py`.

## Vòng 2
QA VERDICT: PASS. Hai xfail của vòng 1 đã gỡ nhãn và pass. 199 passed, 0 skip, 0 xfail (5 file; `CODEX_BRIDGE_ENABLED=false`). `ruff check .` sạch; `hgraph check` sạch.
- AC4: 14 mẫu ref x 3 trường (summary/expectation/evidence) đều bị che (`[1:7]`, `` `12:3` ``, `ref=2:15.`, nhiều ref một chuỗi, 5 chữ số, `1:7:8`, ngoặc/nháy/xuống dòng); quét toàn JSON gói vết bằng `\d+:\d+` không còn mẫu. Hash xác định, kiểm lại được sau che. Text 1000 ký tự toàn ref vẫn dựng được.
- operation_id không phải UUID và target_url > 2000 ký tự: `AgentTaskTraceRefused("evidence_unavailable")`, không crash.
- Replay DB cục bộ chỉ đọc: 217 phiên, `{'unavailable refused assessment_unavailable': 45, 'completed built': 169, 'completed refused operation_failed': 3}`, violations 0 (mẫu ref quét rộng `(?<!\d)\d+:\d+(?!\d)|version:` trên toàn gói, trừ `target_url`), gồm phiên e660f6a3.
- Trần đã biết, không tính FAIL: giờ `12:30`/tỉ số `3:1` bị che; giá trị gõ model trích trong free text không loại được.
- Chưa test: ref viết dạng khác chữ số (vd "version 1 node 7") không bị che theo thiết kế.
