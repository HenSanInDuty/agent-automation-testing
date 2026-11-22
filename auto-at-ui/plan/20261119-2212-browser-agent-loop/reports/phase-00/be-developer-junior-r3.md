STATUS: DONE

# r3 — Chạy nốt 21 test còn thiếu của tests/test_vision_page_batch.py (phase-00, G3b1)

CONTEXT_CHECK
- conventions: thiếu. Lượt này chỉ chạy test, không sửa file nào trong repo nên không đọc docs/api-conventions.md và không chạy hgraph brief.
- graphs: không áp dụng (không sửa file).
- blast radius: không áp dụng (không sửa file).

## Kết quả tóm tắt

- Collect `tests/test_vision_page_batch.py`: 81 test, exit 0 (1.45 s).
- 21 test còn thiếu (theo r2): **21 passed, 0 failed, 0 skipped**, chia 3 lệnh, tổng thời gian pytest khoảng 352 s.
- Không lệnh nào timeout. Không có test đỏ trong lượt này.
- Tổng pytest mới: **1292 passed, 1 failed, 20 skipped** (xem mục Tổng).

## Đối chiếu node id

- Lệnh collect: `CODEX_BRIDGE_ENABLED=false uv run pytest tests/test_vision_page_batch.py --collect-only -q -p no:cacheprovider`. Kết quả: 81 node id, exit 0. Danh sách lưu tại scratchpad `collect.txt`.
- r2 ghi "60 test đã chạy là test thứ 78-137 của chunk G3b1, 21 test chưa chạy là test thứ 138-158 của chunk". Chunk bắt đầu từ `test_vision_[m-r]` nên test đầu tiên của `test_vision_page_batch.py` là chunk #78. Suy ra: 138-158 của chunk = test thứ 61-81 trong thứ tự collect của file.
- 21 node id được chạy (thứ tự collect 61-81):
  - `test_restored_tabs_and_viewport_coverage_keep_verified_targets[visual_deep_twenty]`, `[visual_deep_ten]`, `[visual_mutation_queue]`, `[visual_mutation_queue_form]`, `[visual_mutation_queue_limit]`, `[visual_panel_order]`, `[visual_noop_batch]`
  - `test_restored_tabs_and_viewport_coverage_keep_verified_targets[visual_delayed]`, `[visual_empty]`
  - `test_popup_restore_uses_returned_page_scroll_and_never_replays_effects[stable]`, `[form_drift]`, `[state_limit]`, `[history_delay]`, `[history_stuck]`
  - `test_popup_restore_uses_returned_page_scroll_and_never_replays_effects[history_duplicate]`, `[history_duplicate_form]`, `[history_overwritten]`, `[history_scroll_reset]`, `[history_scroll_reset_form]`, `[history_scroll_reset_up]`, `[mutation_cross_viewport]`
- Ràng buộc: log r2 chỉ có dấu chấm, không có tên test, nên không kiểm chứng được 60 test cũ theo tên. Con số 60 và 21 khớp với tổng 81 và với số liệu r2 (pieceA 12 test + 48 test đầu của chunk). Xem mục Rủi ro.

## Lệnh đã chạy

Mọi lệnh có: `CODEX_BRIDGE_ENABLED=false`, `-p no:cacheprovider -q`, `--basetemp` trong scratchpad, `timeout 540`, stdin `</dev/null`.

| Nhóm | Node id | Basetemp | Kết quả pytest | Thời gian (wall) | exit | Log |
|---|---|---|---|---|---|---|
| 1 | local 61-67 (7 test, `visual_deep_twenty` … `visual_noop_batch`) | scratchpad `pytest-tmp-1` | 7 passed, 8 warnings | 137 s | 0 | `pytest-B-g3b1-page-batch-1.log` |
| 2 | local 68-74 (7 test, `visual_delayed`, `visual_empty`, `popup…[stable]` … `[history_stuck]`) | scratchpad `pytest-tmp-2` | 7 passed, 8 warnings | 105 s | 0 | `pytest-B-g3b1-page-batch-2.log` |
| 3 | local 75-81 (7 test, `popup…[history_duplicate]` … `[mutation_cross_viewport]`) | scratchpad `pytest-tmp-3` | 7 passed, 8 warnings | 118 s | 0 | `pytest-B-g3b1-page-batch-3.log` |

Không nhóm nào vượt 540 s nên không cần chia nhỏ tiếp. Trung bình khoảng 15-19 s mỗi test (7 test mỗi nhóm trong 102-134 s), nhanh hơn ước lượng 30-40 s của r2. Không đo thời gian riêng từng test.

## Tổng pytest mới

Số của r2 (đã kiểm tra lại phép cộng): G1 458 + G2 84 + G3a 251 + G3b1-rest 236 + G3b1 page_batch 60 + G3b2 182 = 1271 passed. Skip: G1 19 + G2 1 = 20. Fail: 1.

Cộng lượt này: +21 passed.

| | passed | failed | skipped |
|---|---|---|---|
| r2 | 1271 | 1 | 20 |
| r3 (21 test page_batch) | +21 | 0 | 0 |
| **Tổng mới** | **1292** | **1** | **20** |

Test đỏ duy nhất (từ r2, không chạy lại trong lượt này): `tests/test_codex_bridge_benchmark.py::test_offline_manifest_provenance_and_explicit_live_boundary`, log `pytest-B-g1-basetemp.log` (G1, 1 failed, 458 passed, 19 skipped). Lỗi là `assert manifest["live_canary"] in {"not_run", "blocked", "passed"}`.

Lưu ý: tổng này gồm 1 test đỏ từ r2. Phase 0 chưa xanh hoàn toàn nếu tính test đỏ đó.

## Artifact benchmark

- Lệnh: `git diff --stat -- benchmark/vision/visual-buttons/flow-result.json`.
- Kết quả: **rỗng**. `git status --short` cho file đó cũng rỗng.
- Ý nghĩa: sau khi test page_batch chạy đủ 81 test, file đã trở về đúng nội dung đã commit. Trạng thái ` M` ghi trong r2 (`"operations": 99 → 96`, `"model_batches": 6 → 5`) không còn. Không khôi phục thủ công. Không sửa file này.

## Rủi ro và việc còn lại

- Ánh xạ 21 test theo chỉ số collect là suy luận từ con số của r2. Nếu r2 có chạy đúng 60 test khác thứ tự, tập 21 có thể sai. Xác minh chắc chắn cần log có tên test (`-v` hoặc `-rA`). Chưa làm vì ngoài phạm vi lượt này.
- Test đỏ `test_offline_manifest_provenance_and_explicit_live_boundary` vẫn còn. Việc này thuộc phạm vi khác (không phải page_batch), chưa điều tra.
- Các việc còn lại từ r2, ngoài phạm vi lượt này: `hgraph check --changed` exit 1 vì `reports/phase-00/v4_identity.py` chưa thuộc graph nào; cần user chọn graph.

## GRAPH_UPDATE

- graph đã cập nhật: không cần — không thêm/xoá file code, không đổi quan hệ import. Chỉ tạo file báo cáo và log trong `reports/phase-00/`.
- file mới đã đưa vào graph: không có.
- hgraph check --changed: không chạy trong lượt này (không đổi code). Kết quả gần nhất ở r2: exit 1, xem `hgraph-check-r2.log`.

## Dọn dẹp

- Các tiến trình pytest đều kết thúc khi lệnh trả về (exit 0). Không có server, stack docker hay tiến trình nền nào được mở.
- Không sửa code, test, `.env`. Không commit. Không chạy migration.
