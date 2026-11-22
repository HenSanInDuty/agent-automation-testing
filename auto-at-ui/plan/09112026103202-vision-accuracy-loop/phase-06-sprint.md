---
status: in_progress
day: 1-done
started: 2026-11-22
deadline: 2026-11-24 (3 ngày làm việc)
live_run_budget: 8
live_runs_used: 2
---
# Phase 06 — Sprint 3 ngày: đóng lỗi round 21 rồi qualification (engine v4 + Claude)

## Phạm vi

Engine v4 (`codex-dom-v11`), provider `claude_cli / claude-opus-5-5`, oracle **v2**
(`oracle-mongchiton-1280-v2.json`, `2795c44f…`), caps/prompt không đổi. Agent loop đóng băng.
Không thuộc sprint: calm mode ADR-043, settle/`mount-switcher`, restoration terminal `unsafe_replay`
(không ảnh hưởng điểm; báo cáo như giới hạn), mct-57 (để là miss được phép), nới guard runtime.

## Ngày 1 — offline (XONG 2026-11-22)

- [x] Xác minh 3 key lạ = 3 bản sao khung video mct-47 (dò ngược descriptor key + probe chỉ đọc).
- [x] Oracle v2 + bằng chứng `video-copies-probe-20261122.json`; v1 giữ nguyên.
- [x] Harness hỗ trợ `alternate_paths`; `rescore.py`; test `tests/test_vision_accuracy_oracle_v2.py`.
- [x] Chấm lại r21: v1 tái tạo điểm gốc; v2 passed (C=A=46/47, P=R=47/47).
- [x] Commit (được phép 2026-11-22): `d351561` phần agent loop trước sprint; commit sprint ngày 1 kế tiếp.
- [x] Tiêu chí 4/5 → `metrics.qualify_batch` + test.

## Ngày 2 — chuẩn bị chạy rồi 1–3 live run thử

Rủi ro đã biết: source hiện tại ≠ source r21 (`fbc60836…`). Thay đổi agent-loop vào tree sau r21,
và **ADR-042 (settle geometry tolerance) không nằm sau cờ agent mode** nên áp dụng cả v4; cùng với
fix `__name`, RustFS read-after-write đã có ở r21. Vì vậy lượt đầu là lượt thử cho source mới.

1. **Regression v4 trên source hiện tại** (không chạy cạnh live):
   worker `npm.cmd run typecheck` + `vision-operations.spec.ts`, `vision-visual-buttons.spec.ts`,
   `vision-readiness.spec.ts`, `vision-settle-animation.spec.ts`; Python
   `uv run python benchmark/vision/codex/run_offline.py -q --tb=short tests/test_vision_page_batch.py
   tests/test_codex_revalidation.py tests/test_vision_live_persistence.py` (+ `--basetemp` nếu cần).
   Sửa test manifest-hash drift (`benchmark/vision/codex/manifest.json`) bằng regenerate, không tắt test.
2. **Runner v4 có theo dõi**: nâng `.pytest-artifacts/accuracy_round.py` thành
   `benchmark/vision/accuracy/round_v4.py` với `preflight | start | collect | score`, mặc định oracle v2,
   original session `d69fc7fa-…`, policy `claude_cli`. `preflight` = smoke gate bắt buộc:
   - không có session active; tenant policy đúng provider/model/consent đã ghi;
   - checksum file trong container khớp tree (control-plane, temporal-worker, playwright-worker,
     claude-bridge); worker HTTP 401 trên `/visual-explorations`; bridge heartbeat `online` ≥60 s;
   - token bridge còn ≥3 giờ (`scripts/export_claude_bridge_token.py` nếu không);
   - mở/đóng một session worker không LLM thành công (bắt loại lỗi `__name`/cold start).
   Preflight fail → không submit, không tính vào ngân sách.
3. **Chấm tự động** (`score`): bind dom_path theo oracle v2; outcome tự động khi luật máy kết luận được
   (URL fingerprint khớp đích đã khai báo/redirect review; `#true` cho mct-47; download chain; tab/character
   active) — còn lại (carousel, empty search, TOP) xuất danh sách để review ảnh. Mỗi lượt có điểm thật.
4. **Live thử** 1–3 lượt (trong ngân sách 8). Lượt trượt → sửa đúng lỗi đó (red→green), một reviewer.

## Ngày 3 — qualification

- Đóng băng source/config/oracle/image digest; chạy **5 lượt liên tiếp** với một lần duyệt cho cả loạt;
  báo cáo đủ 5 lượt, không bỏ lượt nào.
- Tiêu chí (chốt 2026-11-22): ≥4/5 lượt đạt mọi gate + safety 0 ở cả 5 lượt + ≥100 interaction
  attempts tổng (`metrics.qualify_batch`); báo thêm "3 lượt liên tiếp" để tham chiếu.
- Report `benchmark/vision/accuracy/QUALIFICATION-<date>-sprint.md` + JSON (hashes, run IDs, raw counts,
  missing/wrong targets, calls/tokens).

## Điểm dừng

Hết 2026-11-24 hoặc hết 8 live run (tính cả lượt thử) → dừng, viết báo cáo bằng số thật (r16 đạt theo v1,
r21 đạt theo v2 khi chấm lại, kết quả sprint), không mở vòng lặp mới nếu người dùng không quyết định lại.

## Nhật ký

Ghi ngắn trong `log.md` (mỗi lượt ≤10 dòng). Không phình README.
