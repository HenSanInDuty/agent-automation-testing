STATUS: DONE

# artifact r2 - phase 04, agent loop round 01 r7

## Đã sửa
1. `progress.html` (chỉ Edit, không publish):
   - Sub-header: "r5 sang r6, r7".
   - Bảng trạng thái, dòng phase 04 (vẫn in progress): thêm tóm tắt r7 vào cột Validation.
   - Thêm 1 section mới "Phase 04: agent loop round 01 r7, hai hướng offline" sau section r5-r6: mục tiêu/người làm, bảng lượt, Diff thật (A và B), Database, Test, Convention/graph/ponytail, Quyết định cần user (A1-A3, B). QA ghi "Bỏ qua theo quy tắc".
2. `README.md` (canonical): nối cuối file mục `### Agent loop round 01 r7 handoff - 2026-11-21` (10 dòng gồm tiêu đề, bullet). Nội dung cũ không sửa. `phase-04-iterate.md` không đụng.

## Số liệu diff dùng (git diff --numstat / status --short / wc -l, trong auto-at-ui)
Hướng A:
- evidence.py: M, +108/-3 · run.py: M, +84/-24 · benchmark/vision/accuracy/README.md: M, +20/-0
- AGENT-LOOP-01-20261120.md: ?? 266 dòng · tests/test_vision_accuracy_binding.py: ?? 379 · docs/adr/039-...md: ?? 58 · docs/graphs/vision-accuracy-harness.md: ?? 82
- runs/1c56623e-.../ : ?? (thư mục untracked, thêm grounding.json, rescore-role-binding.json), không đếm dòng.
Hướng B:
- vision-checkpoints.ts: M, +37/-1 · vision-observability.spec.ts: M, +27/-0
- vision-operations.ts: M, +94/-12 (tổng so với HEAD, file bẩn từ trước; phần B theo báo cáo dev: 1 chỗ observeDom)
- playwright-vision-worker.md: M, +90/-72 (tổng so với HEAD; phần B: 1 bullet tay)
- vision-agent-mode.spec.ts: ?? 431 dòng (phần B: +7 test)

## Ghi chú
- Số test, ESCALATE, hgraph, lint lấy nguyên từ be-developer-r6a/r6b và leader-r2a/r2b; không chạy lại test.
- Git cảnh báo LF->CRLF khi chạy diff (chỉ cảnh báo).
