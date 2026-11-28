# QA phase 03 — test report

QA VERDICT: PASS (phase 03; chưa phải phase cuối)

## Môi trường
Windows host, `uv run pytest` với `CODEX_BRIDGE_ENABLED=false`, postgres fixture 55437 thật (không skip test DB); stack compose đang chạy build từ code hiện tại (prompt `agent-loop-v4`); phiên thật qua bridge Claude, token còn hạn (không phiên nào `bridge_model_unavailable`). Không commit.

## Kết quả
- Automation mới: `tests/test_qa_p3_page_text_snapshot.py` — 26 pass, 4 skip (payload bị contract từ chối trước renderer).
- Nhóm tiêu chí 4: `293 passed, 10 skipped` (10 skip = test bridge-process chỉ chạy trong container Linux). Nhóm contract/benchmark: `257 passed, 7 skipped` (gồm 4 skip của Q, 3 skip "offline harness image" ở benchmark).
- `uv run ruff check .`: `All checks passed!` (sau khi tôi sửa 2 dòng dài trong file test của mình).
- Chạy thật (`--out .pytest-artifacts/task-stability/p3qa`, 5 phiên, `Verdict: STABLE`, 5/5 completed, expected match 100%):

| Task | Kỳ vọng | Kết quả | Lượt model |
|---|---|---|---|
| login-failure | achieved | achieved | 2 (dom, dom) |
| broken-save | not_achieved | not_achieved | 2 (dom, dom) |
| broken-counter | not_achieved | not_achieved | 2 (dom, dom) |
| search-results | achieved | achieved | 3 (dom, dom, image) |
| modal-open-close | achieved | achieved | 3 (dom x3) |

3 task phụ thuộc chữ: 2 lượt/phiên, không xin ảnh (r3 ~3 lượt/phiên; 1 mẫu/task nên chỉ là chỉ báo). Worker Playwright ghi 25 sự kiện `vision.dom.page_text` trong 20 phút gần nhất. Số lượt đọc từ bảng `codex_bridge_jobs` theo session id trong `p3qa/runs.jsonl`.

## Tiêu chí
1 PASS (Q01, Q02). 2 PASS ở mức unit/differential (Q03-Q07, Q09-Q11, Q14); injection thật chỉ ở mức unit (L7). 3 PASS (Q12, Q13, DEV). 4 PASS. 5 PASS (Q09-Q11). 6 PASS (L1-L6). 7 PASS (ruff, benchmark; `refresh_manifest.py` do dev chạy, "0 refreshed" — tôi không chạy lại, test benchmark qua).

## Phát hiện không chặn
- N1: `json.dumps(ensure_ascii=False)` để nguyên U+2028/U+0085 trong dòng chữ (Q08). Contract `CodexPageTextItem` hiện từ chối ký tự điều khiển/dấu tách dòng ở Q07 (4 payload skip), nên chỉ lọt nếu `validate_locator_value` cho qua U+2028 riêng lẻ; trong test Q08 chuỗi `a b\x85c` VẪN được contract nhận. Tác động thấp (không tạo dòng control giả với `\n`-split; chỉ `splitlines()` thấy là dòng mới, và model đọc chữ trong dấu nháy). Giống hành vi tên control từ trước. Gợi ý (không bắt buộc): dùng `ensure_ascii=True` cho chữ trang hoặc loại U+2028/2029/0085 ở contract.
- N2: `page_text_truncated=True` mà không có mục và không có `skipped` thì không in gì (agent không biết chữ bị cắt). Worker không phát tổ hợp này trong thực tế (cắt thì đã có mục); Q06 ghi hành vi hiện tại.
- N3 (`tests/test_qa_r8_agent_evidence.py:370`): xác minh độc lập là có từ HEAD. `git show HEAD:auto-at-ui/workers/playwright/src/vision-dom.ts` không chứa chuỗi `type === "password" || type === "hidden"` (đếm 0) và có dòng 110 `if (type === "hidden" || (type === "password" && !credentials))`; file test không bị sửa so với HEAD. Do phase 01, không phải phase 03. Không sửa.
- Hard cut: `render_snapshot` vẫn cắt cứng `[:max_chars]` ở cuối như HEAD; với URL trang rất dài (>3000 ký tự) header có thể làm cắt giữa mục chữ. Hành vi cũ, URL thật bị giới hạn ở tầng khác; không kiểm vì ngoài phạm vi.
- Phiên `search-results` xin ảnh và `modal-open-close` mất 3 lượt dom: biến thiên bình thường của agent, kết quả đúng; không phụ thuộc đường chữ trang như bằng chứng lỗi.

## Chưa test được
- Prompt-injection thật qua trang: fixture `task-ui` không có đường phản chiếu input vào alert/status/heading (chữ là hằng; input chỉ vào value/aria-label/li). Không sửa fixture theo chỉ đạo; đã phủ unit (Q07, Q14, test của dev `test_page_text_reaches_the_model_and_cannot_change_what_the_platform_allows`, `test_hostile_page_text_stays_data_...`). Không thấy đường nào chữ trang đổi hành vi agent ngoài task.
- Nội dung prompt thực gửi bridge cho từng phiên: bảng chỉ lưu hash; chỉ có bằng chứng gián tiếp (summary trích đúng chữ trang, sự kiện `vision.dom.page_text`).
- `refresh_manifest.py` không chạy lại (dev báo 0 refreshed, benchmark test qua).
- Không chạy `tests/test_vision_page_batch.py` (dao động sẵn trên Windows, ngoài blast radius trực tiếp).

## Graph
`hgraph add vision-agent-loop tests/test_qa_p3_page_text_snapshot.py` rồi `hgraph check`: `7 graph, 530 file source — Không có vấn đề.` `hgraph check --changed` vẫn báo `[uncovered-changed]` 15 file (agent_loop.py, vision_agent_loop.py, codex_bridge.py, vision_worker.py, 6 file test, 5 file worker TS): false positive đã biết khi chạy từ `auto-at-ui/` (đường dẫn `auto-at-ui/...` không khớp index; `hgraph which tests/test_vision_agent_loop.py` xác nhận file thuộc graph). File test QA mới không nằm trong danh sách này.

## Dọn dẹp
Không mở tiến trình/stack nào; stack compose và postgres fixture giữ nguyên.
