QA VERDICT: PASS

# QA phase 16 (cuối plan) — báo cáo, vòng r1

Môi trường: HEAD `d7d2b06` + thay đổi chưa commit; Windows host (Python qua `uv`, node); container tạm `qa16-pg` (postgres 17, cổng 55437) + `qa16-pytest` (image `auto-at-ui-control-plane`, repo chép vào `/tmp/repo`, `CODEX_BRIDGE_ENABLED=false`, `-p no:cacheprovider`); stack đang chạy chỉ được đọc (`SELECT`, `docker logs`). Hai container tạm đã xoá (`docker ps -a | grep qa16` = 0). Không chạy model, không rebuild/restart stack, không đụng `makemoney-*`.

## 1. Kiểm chứng độc lập dữ liệu r2 (DB thật, chỉ đọc)

- Run: 22 run trong `state.json` đều có trong `test_runs`, trạng thái DB khớp state 22/22. Phân bố: login 1 first + 5 rerun `passed`; todo 1 + 5 `passed`; search 1 + 5 `passed`; `e2e-1` first `passed`, run sau phá (`b4de3ea8`) `failed`; `e2e-2` `failed`; `marker-todo` `failed`. 15 rerun dùng đúng `test_case_id` của draft tương ứng.
- Draft: 6 draft trong state đều `approved`, `provenance.requested_by = task-e2e-requester`, `generated_test_decisions.decided_by = task-e2e-reviewer`, `approved = t`, `linked_run_id` khớp state.
- Nơi lưu giá trị (quét 30 bảng public trừ `alembic_version`, `json_each_text(row_to_json(x))`, thô + thoát `\uXXXX` một và hai lớp):
  - `Demo1234`: `generated_test_drafts.playwright_test_source`, `outbox_events.payload`, `test_cases.specification`, `test_runs.request` + chữ tự do `visual_agent_steps.memory/evaluation_previous_goal`, `visual_exploration_sessions.task_assessment`.
  - `Viết báo cáo` (bản thoát): cùng bốn nơi khai báo (5/15/5/15 hàng) + cùng cột chữ tự do (+ `next_goal`).
  - `balo`: bốn nơi khai báo + cột chữ tự do.
  - `ZQ4471-todo1` (chỉ nhập lúc xin draft): CHỈ bốn nơi khai báo (3/3/3/3); DB phiên, `visual_agent_steps`, `audit_events`, `generation_requests` sạch.
  - `audit_events`, `generation_requests`, `idempotency`: không có hàng nào cho cả bốn giá trị.
- Log `docker logs --since 12h` của control-plane, temporal-worker, playwright-worker, claude-bridge: 0 lần cho `Demo1234`, `ZQ4471`, `Viết báo cáo` và dạng thoát. Phụ thuộc cửa sổ 12 giờ; không quét Loki/fluent-bit.
- Không quét lại artifact (trace zip) ở vòng này; dựa bảng của dev r2 (4 run, `unexpected_members` rỗng) và `test_qa_p15c_fixes.py::test_f3_*` ghim danh sách thành viên.

## 2. Automation (output thật)

```
# container, DB thật
e2e + task_stability:                                     72 passed, 5 warnings in 31.35s
agent_task_* + qa_p08/p09/p10..p15c + phase14 + policy_audit
  + reporting_event_processor + task_stability + verified_text:
                                                          845 passed, 26 skipped, 2 xfailed in 239.51s
generation* + qa_p2/p3 + phase01 + assessment:            4 failed, 204 passed, 8 skipped
   (4 fail = test_qa_p3_*: FileNotFoundError 'git' trong container; môi trường, không phải sản phẩm)
# host (có node; ca DB skip)
qa_p3 + p15c + p11 renderer + renderer + e2e + task_stability: 281 passed, 30 skipped, 1 xfailed in 109.79s
tests/test_qa_p16_e2e.py (mới):                           8 passed in 0.27s
# JS
apps/dashboard: tsc --noEmit sạch; npm test: tests 80 / pass 80 / fail 0
workers/playwright: tsc --noEmit sạch
# lint
uv run ruff check .  -> 1 lỗi: benchmark\vision\accuracy\run.py:292 E501 (104 > 100)
```

Lỗi ruff nằm ngoài phase 16 (file do phiên khác sửa; dev r2 đã báo). Test mới của QA và file phase 16: `ruff` sạch (đã `--fix` import order của file QA). Skip 26 ở container = ca cần node/tsx (đã chạy ở host).
Chênh lệch số (dev báo 882 passed ở nhóm gần giống; QA 845): QA chưa xác định tập file dev dùng; nhóm của QA không có ca fail và con số 845 trùng lượt dev ghi "trước khi thêm ca" ở r2.

## 3. Graph

```
$ hgraph check            -> 8 graph, 560 file source / Không có vấn đề.
$ hgraph check --changed  -> File vừa đổi: 74; [uncovered-changed] toàn đường dẫn tiền tố `auto-at-ui/`
```
`--changed` là false positive đã biết (git root ở thư mục cha, file tracked chưa commit). Kiểm riêng từng file untracked `.py/.ts/.tsx/.mjs` bằng `hgraph which`: tất cả thuộc graph, trừ `tests/test_qa_p15c_fixes.py` (file test QA của phase 15c, chưa thuộc graph nào; phase trước cũng không thêm file test QA vào graph; `tests/test_qa_p16_e2e.py` của QA cũng vậy). Ghi nhận ở mức thấp, không chặn.

## 4. F5 và F4

F5 (`agent_task_renderer.py::_candidate_lines`): ĐÃ TÁI HIỆN bằng test đơn vị (`test_f5_01`): `fill` dùng giá trị người yêu cầu nhập, assertion vẫn đòi chữ trang chứa giá trị agent đã gõ. Ảnh hưởng chỉ về phía an toàn (false `failed`, không bao giờ `passed` nhầm; r2: marker `failed` 2/2). Không tiêu chí nào của phase 16 hay AC1–AC7 đòi test chạy `passed` với giá trị khác phiên: tiêu chí 1/2 chỉ đo test với giá trị của phiên; AC4/AC3 không nói về assertion. Nhưng nó làm mất một phần giá trị của thiết kế "người A nhập giá trị của họ" (ADR-047: giá trị do người yêu cầu cung cấp): bất kỳ giá trị khác giá trị trong câu task đều làm test `failed` khi assertion chứa nó. Mức: trung bình về chức năng, không phải lỗi an toàn. KHÔNG tính là FAIL của phase 16; phiên chính hỏi user (tham số hoá assertion theo giá trị hay loại ứng viên chứa giá trị gõ; lưu ý trace không chứa giá trị gõ nên renderer không biết chuỗi nào cần loại, nên cần thêm thông tin từ phiên khi dựng ứng viên).

F4 (`search-results` chỉ assert điều khiển): ĐÃ TÁI HIỆN (`test_f4_01`): hai ứng viên `control_name` -> hai dòng `getByText/getByLabel ... toBeVisible`, không có chữ kết quả. `passed` của test này không chứng minh kết quả tìm. AC1 chỉ đòi "chạy `passed`" và test không pass nhầm trên fixture phá cố ý; ca (b) phá chữ chạy trên phiên `e2e-1`; QA không xác nhận được ca phá riêng cho `search-results` đã chạy. Không vi phạm chữ AC; là nợ chất lượng đã ghi (user chưa quyết). Mức: trung bình (test yếu), không FAIL.

## 5. Chưa test được / chưa phủ

- Chạy lại thật qua API (mục tuỳ chọn 4): không làm; 15/15 từ r2 đã đối chiếu DB, nên không thêm giá trị đủ lớn so với rủi ro tạo run/bàn giao quyền.
- Ca âm a–j không chạy lại độc lập trên stack (tốn phiên model/ghi DB); dựa events r2 và ca DB tự động (e2e 29 ca đều pass).
- Artifact thật (trace zip) không quét lại; screenshot không xem bằng mắt (r2 cũng không quét byte png).
- Log ngoài cửa sổ 12 giờ, Loki/fluent-bit, workflow history Temporal: không quét (như r2).
- Dashboard e2e: image dashboard cũ trên stack; UI form 4b chỉ kiểm qua API/test (`tests 80 pass`).
- Stress test: không cần, không đụng vòng lặp lớn, truy vấn không index, job hàng loạt hay transaction/lock.

## 6. Phán quyết

QA VERDICT: PASS. Mọi AC ADR-047 và tiêu chí 1–8 của phase 16 có bằng chứng; dữ liệu r2 khớp DB thật; không phát hiện nơi lưu giá trị ngoài danh sách. Ghi chú không chặn: ruff 1 lỗi ngoài phạm vi (`benchmark/vision/accuracy/run.py:292`), F4/F5 chờ user quyết, `tests/test_qa_p15c_fixes.py` chưa vào graph.
