---
phase: 3
title: Verify and Smoke Test
status: completed
priority: P2
effort: 1h
dependencies:
  - 1
  - 2
---

# Phase 3: Verify and Smoke Test

## Overview

Xác minh thay đổi chạy đúng và **không hồi quy admin**. Build + lint + smoke test thủ công luồng user.

## Requirements

- Build `user-app` và `shared` pass, không lỗi TypeScript.
- Lint không có unused import/var mới.
- Admin run page giữ nguyên đầy đủ (LLM Profile + Pause/Cancel + summary cũ).

## Implementation Steps

1. **Typecheck/build**:
   - `npm run build:user` — build user-app (gồm cả `@auto-at/shared`).
   - Nếu muốn chắc chắn không vỡ admin: `npm run build:admin`.
2. **Lint**: `npm run lint` (workspaces) — sửa unused import nếu có (chủ yếu file Phase 2).
3. **Smoke test thủ công (user-app)** — `npm run dev:user` (port 3002), đăng nhập tài khoản non-admin:
   - `/pipelines`: không còn ô search; các card hiện đầy đủ; bấm "Run pipeline".
   - Trang run: KHÔNG có dropdown LLM Profile, KHÔNG có nút Pause/Cancel; CÓ Document upload + nút Run.
   - Upload 1 tài liệu mẫu (hoặc chạy không file nếu template cho phép) → bấm Run → thấy `RunInProgressCard` → khi xong thấy `TerminalSummaryCard` + **ResultsViewer inline** với kết quả đầy đủ ngay tại trang.
4. **Regression admin (`npm run dev:admin`)**: mở trang run của admin → vẫn còn LLM Profile + Pause/Cancel; sau khi chạy vẫn là summary + link (KHÔNG bị ép inline). Xác nhận props mặc định giữ hành vi cũ.
5. **GitNexus**: chạy `gitnexus_detect_changes()` trước khi commit để chắc chỉ ảnh hưởng các symbol dự kiến (`PipelineRunPage`, user-app pages).

## Todo List

- [ ] `npm run build:user` pass
- [ ] `npm run build:admin` pass (regression)
- [ ] `npm run lint` sạch
- [ ] Smoke test user: bỏ chọn + kết quả inline OK
- [ ] Regression admin: giữ nguyên đầy đủ
- [ ] `gitnexus_detect_changes()` đúng scope

## Success Criteria

- [ ] Tất cả build + lint pass.
- [ ] Luồng user: run + xem kết quả inline, không có lựa chọn LLM/Controls/search.
- [ ] Admin không thay đổi hành vi.

## Risk Assessment

- **Backend cần đang chạy** để smoke test thật (WS + API). Nếu không có backend, tối thiểu verify build/lint + render trạng thái idle/loading.
- **System Default LLM phải tồn tại** ở môi trường test, nếu không run sẽ lỗi — đây là dữ liệu môi trường, không phải lỗi code.
