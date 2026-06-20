---
title: Simplify User Pipeline Run Experience
description: ''
status: completed
priority: P2
branch: develop
tags: []
blockedBy: []
blocks: []
created: '2026-06-01T22:21:06.840Z'
createdBy: 'ck:plan'
source: skill
---

# Simplify User Pipeline Run Experience

## Overview

Mục tiêu: end-user (non-admin) chỉ cần **chạy** pipeline và **xem kết quả ngay tại chỗ**, không phải "chọn" gì.

Quyết định đã chốt với user:
- **Ẩn** ở trang chạy của user: LLM Profile selector, nút Pause/Cancel.
- **Giữ** Document upload (đây là input thật, backend nhận `file?` optional).
- **Bỏ** thanh search ở trang danh sách pipeline (`/pipelines`).
- **Kết quả**: render `ResultsViewer` full inline ngay trên trang chạy sau khi run kết thúc (không bắt user bấm sang trang khác).
- **Phạm vi**: chỉ ảnh hưởng `user-app`. `PipelineRunPage` là component dùng chung trong `packages/shared` (admin-app `export *` lại) → thêm **props opt-in** (mặc định = hành vi cũ) nên admin **không đổi**.

Approach: KISS/DRY — không fork component. Thêm 3 prop optional vào shared `PipelineRunPage`; `user-app` bật chế độ đơn giản; sửa trực tiếp file list page của user-app (không shared).

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Extend Shared Run Page](./phase-01-extend-shared-run-page.md) | Completed |
| 2 | [Simplify User App](./phase-02-simplify-user-app.md) | Completed |
| 3 | [Verify and Smoke Test](./phase-03-verify-and-smoke-test.md) | Completed |

## Key Files

- `packages/shared/src/components/pipeline/PipelineRunPage.tsx` (855 dòng) — component dùng chung, sửa ở Phase 1.
- `packages/shared/src/components/pipeline/ResultsViewer.tsx` — props `{ run, templateNodes? }`, render inline.
- `apps/user-app/src/app/pipelines/[id]/run/page.tsx` — wrapper user-app, truyền props ở Phase 2.
- `apps/user-app/src/app/pipelines/page.tsx` (491 dòng) — list page, bỏ search ở Phase 2.
- `apps/admin-app/src/components/pipeline/PipelineRunPage.tsx` — chỉ re-export, **không sửa** (verify giữ nguyên).

## Dependencies

- Không có cross-plan dependency (2 plan dang dở khác về tooling ClaudeKit, không đụng FE).
- Phase 2 phụ thuộc Phase 1 (cần props mới). Phase 3 phụ thuộc Phase 1+2.
