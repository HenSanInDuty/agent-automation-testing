QA VERDICT: PASS

# QA phase 17 — F5 `derived_from_typed` (F4 chuyển phase worker)

Môi trường: HEAD `d7d2b06` + thay đổi chưa commit; stack thật (control-plane + temporal-worker build lại từ code hiện tại, claude bridge, fixture `task-target`); host Windows (uv, node); container tạm `qa17-pg` (postgres 17, `-c port=55437`, không publish cổng) + `qa17-pytest` (image `auto-at-ui-control-plane`, chung network namespace, repo chép vào `/tmp/repo`, `uv sync --frozen --group dev --no-install-project`, không cài basedpyright/ruff/nodejs). Hai container đã `docker rm -f` (`docker ps -a | grep qa17` = 0).

## Kết quả

- Tiêu chí 1, 2, 3, 4, 5, 6: đạt (xem `test-cases.md`, 21 ca PASS, 1 ca không kiểm chứng trực tiếp).
- Nhóm DB `tests/test_vision_verified_text.py tests/test_agent_task_trace.py tests/test_vision_agent_loop.py tests/test_vision_agent_task_assessment.py`: `197 passed, 1 warning` — DB skip = 0. Hai test loop mới (`test_a_candidate_holding_a_value_the_agent_typed_is_marked_in_the_stored_assessment`, `test_nothing_typed_in_the_session_leaves_the_stored_shape_unchanged`) PASS.
- Hồi quy container: `test_agent_task_*`, `test_qa_p08..p16`, `test_qa_p17` → 789 passed, 32 skipped (node/tsx/artifact r2), 2 xfailed; 3 fail đầu tiên do container thiếu thư mục `benchmarks/`, chép vào thì `49 passed, 23 skipped`. Host (có node): `243 passed, 11 skipped, 1 xfailed`. `test_f4_01`/`test_f4_02` pass.
- ruff 9 file đụng: `All checks passed!`.
- E2E (batch `p17`, `.pytest-artifacts/task-draft-e2e-p17/`):
  - phiên marker mới `2d92d9b9`: task_assessment lưu `derived_from_typed: true` cho `hoàn thành: Viết báo cáo` và `Xoá Viết báo cáo`, item `3 việc, 1 đã xong` không cờ.
  - `case def` (marker `ZQ4471-todo1`): d/e/f đúng mã lỗi, approve 200, run `8a30605a` = `passed`. Draft chỉ assert `getByText("3 việc, 1 đã xong")`, không có `hoàn thành: ...`; `stop_conditions` có "2 candidate(s) were left out: their text holds a value typed in the session ...".
  - pos-login, pos-todo, pos-search: first `passed`, 2 rerun mỗi test `passed` (6/6).
  - scan marker: chỉ ở 4 nơi khai báo, `unexpected: []`, log 0.
  - teardown xong; không đụng mongchiton hay localhost:1000. Dữ liệu còn lại trên stack: 3 project hậu tố `p17` và 4 draft/run của batch (sạch được bằng teardown của script chỉ gỡ container e2e).
- `hgraph check`: `8 graph, 562 file source / Không có vấn đề.` `hgraph check --changed` vẫn báo `uncovered-changed` do tiền tố đường dẫn `auto-at-ui/` của file tracked chưa commit (false positive đã biết); không có file phase 17 nào trong danh sách `drift/stale`.
- Stress test: không cần — không đụng vòng lặp lớn, query không index, job hàng loạt, transaction/lock; quy tắc overlap là so chuỗi trên ≤ 200 mục quan sát × vài giá trị gõ.

## Quan sát (không FAIL)

1. Giới hạn đã biết, đã ghim bằng test: Unicode không chuẩn hoá (NFD vs NFC không đánh cờ) — nếu agent trả chữ ở dạng NFD còn trang NFC thì ứng viên lọt cờ và có thể gây `failed` sai như F5 cũ. Hiếm (model/DOM thường NFC); đề xuất `unicodedata.normalize("NFC", ...)` trong `squash` cho phase sau.
2. Đánh đổi cố ý (ADR-047): loại thừa. Login mất assertion "Xin chào, demo"; todo mất `hoàn thành: ...` và control `Xoá Viết báo cáo`; nút/control có tên trùng một phần chữ gõ cũng bị loại.
3. pos-search lượt này `candidates = 0` (trước đây 2 tên điều khiển): draft không có assertion kết quả nào và vẫn `passed`; vì không có ứng viên nên không có ghi chú "left out". Biến thiên theo model, thuộc phạm vi F4/phase worker.
4. Phiên lưu trước phase 17 không có cờ nên draft dựng từ phiên cũ vẫn giữ hành vi cũ (`test_f5_04` ghim).

## Chưa test được

- "Fail trên code cũ" không chạy được: các file phase 08–16 chưa commit nên không có bản HEAD để đối chiếu; dựa vào tính cấu trúc (tham số `typed`, trường contract đóng, ghi chú mới).
- Nhóm test cần node/tsx worker (23 ca `test_qa_p15c_fixes.py` ở container) chỉ chạy ở host; ca DB ở host skip (cổng 55437 không tới được), đã bù bằng container.
- Không chạy `--count 5` reruns, không chạy các ca âm a–j của phase 16.

## Tài liệu / file

- `plan/20261125-2140-agent-loop-task-testing/qa/phase-17/test-cases.md`
- `plan/20261125-2140-agent-loop-task-testing/qa/phase-17/test-report.md`
- `tests/test_qa_p17_typed_flag.py` (mới, 21 ca)
