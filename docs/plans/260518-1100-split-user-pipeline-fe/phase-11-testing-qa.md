---
phase: 11
title: "Testing & QA"
status: pending
priority: P1
effort: "1d"
dependencies: [6, 7, 8, 9, 10]
---

# Phase 11: Testing & QA

## Overview
Validate toàn bộ luồng end-to-end: admin tạo template → user chạy → progress realtime → export. Đảm bảo regression không xảy ra ở admin-app.

## Requirements
- Functional:
  - Acceptance test cho user-app: 3 role × {login, list, run, history, export}.
  - Regression cho admin-app: builder save, clone, archive, delete, LLM/agent/user CRUD.
  - Backend RBAC pytest pass.
- Non-functional:
  - CI script chạy cả admin lint, user lint, backend test.

## Architecture
Test layer:
1. **Manual smoke** — checklist 2 trang dưới đây.
2. **Pytest backend** — RBAC enforcement.
3. **Optional: Playwright** — 1 happy-path cho user-app (login → run → wait terminal).

## Related Code Files
- Create:
  - `backend/tests/test_rbac_enforcement.py`
  - `apps/user-app/e2e/happy-path.spec.ts` (optional, nếu có Playwright)
  - `plans/260518-1100-split-user-pipeline-fe/reports/qa-checklist.md`
- Modify: (none)

## Implementation Steps
1. Tạo `qa-checklist.md` với mọi case sau, đánh dấu khi pass:

   **User-app (port 3002):**
   - [ ] Trang login render, login admin/qa/viewer thành công.
   - [ ] `/` redirect `/pipelines`.
   - [ ] List template hiển thị, **không** có Clone/Archive/Delete menu.
   - [ ] Card không có nút "New Pipeline".
   - [ ] Click card → detail read-only, **không** React Flow builder.
   - [ ] Bấm Run → upload file → start pipeline → WS progress realtime.
   - [ ] Pause/Resume/Cancel hoạt động (qa/admin).
   - [ ] Terminal → TerminalSummaryCard.
   - [ ] `/pipelines/[id]/runs` list run, click → detail run, export HTML/DOCX OK.
   - [ ] Logout → redirect `/login`.

   **Admin-app (port 3001):**
   - [ ] Login admin → builder hoạt động bình thường.
   - [ ] Create template, clone, archive, delete OK.
   - [ ] LLM profile CRUD OK.
   - [ ] Agent config CRUD OK.
   - [ ] User mgmt CRUD OK.
   - [ ] Chat (nếu có) hoạt động.
   - [ ] Run pipeline test trong admin → WS, history, export OK.

   **Backend RBAC pytest:**
   - [ ] viewer write template → 403.
   - [ ] qa start run → 201.
   - [ ] viewer start run → 403.
   - [ ] admin các write → 200.

2. Chạy `npm run build` cho cả 2 app — 0 error.
3. Chạy `npm run lint` cho cả 2 app — 0 new warning.
4. Verify `docker compose up` → cả 5 service backend + 2 FE healthy.

## Success Criteria
- [ ] Mọi checklist trên đều ✓.
- [ ] `pytest backend/tests/test_rbac_enforcement.py` pass.
- [ ] Build cả 2 app sạch.
- [ ] No console error trong DevTools khi chạy happy-path.

## Risk Assessment
- **R**: Test thủ công bỏ sót edge case (browser back, refresh giữa run).
  **Mitigation**: checklist explicit "refresh mid-run", "back-button mid-run".
- **R**: Backend test thiếu coverage → user-app có thể bypass write nếu role check sai.
  **Mitigation**: viết test chạm mọi endpoint write — không chỉ subset.
