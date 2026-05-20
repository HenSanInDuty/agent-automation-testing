---
phase: 7
title: "API + Frontend integration"
status: pending
priority: P2
effort: "1d"
dependencies: [5, 6]
---

# Phase 7: API + Frontend integration

## Overview

Expose pipeline mới qua API + chỉnh sửa FE (admin-app + user-app) để: (1) chọn template `automation-testing-api`, (2) hiển thị lỗi MD spec validation thân thiện (highlight section thiếu), (3) chặn nút download report khi `verified=false` và show verification summary.

## Requirements

**Functional**
- BE endpoint:
  - `GET /pipeline/runs/{id}/report/verification` → trả `VerificationResult`.
  - `GET /pipeline/runs/{id}/report/html|docx` chặn 409 nếu unverified.
- FE:
  - Run create form: file input chỉ accept `.md` khi template là `automation-testing-api`.
  - Khi run failed với `error_type=md_spec_validation`, show alert "MD thiếu section: Endpoint / Request / Response" + link tới contract doc.
  - Run detail panel: card "Report Verification" hiển thị 3 component (test cases / results / unit test files) với badge ✅/❌ và issues list.
  - Disable button "Download HTML/DOCX" khi unverified, show tooltip lý do.

**Non-functional**
- Không thay đổi schema response cũ — chỉ thêm field mới optional.
- I18n: VN/EN cho error message MD spec.

## Architecture

```
shared/api/pipeline.ts
  + getReportVerification(runId)
shared/store/pipeline.ts
  + verification slice
admin-app & user-app
  + RunDetail/ReportVerificationCard.tsx
```

## Related Code Files

- Modify: `backend/app/api/v1/pipeline/results.py` — endpoint mới + 409 guard
- Modify: `backend/app/schemas/pipeline.py` — thêm `ReportVerificationResponse`
- Create: `packages/shared/src/api/report-verification.ts`
- Create: `packages/shared/src/hooks/use-report-verification.ts`
- Create: `packages/shared/src/components/pipeline/ReportVerificationCard.tsx`
- Modify: `apps/admin-app/src/app/pipelines/runs/[runId]/page.tsx` — inject card
- Modify: `apps/user-app/src/app/runs/[runId]/page.tsx` — inject card
- Modify: `packages/shared/src/components/pipeline/RunCreateForm.tsx` (or equivalent) — accept-only-md cho template này

## Implementation Steps

1. BE: thêm endpoint `GET /pipeline/runs/{id}/report/verification` đọc `PipelineResultDocument(stage="reporting", agent_id="report_verifier")` → trả Pydantic response model.
2. BE: trong `GET .../report/{html|docx}`, load verification, 409 với detail nếu fail (admin có thể `?force=true`).
3. FE shared: API client + React Query hook.
4. FE component `ReportVerificationCard`:
   - 3 badge rows (test_cases / results / unit_test_files) với count + ✅/❌.
   - Collapsible "Issues" list.
   - Action button "Download HTML" / "Download DOCX" — disabled if unverified, tooltip giải thích.
5. FE error UX: bắt `error_type=md_spec_validation` từ WebSocket / run detail → render structured alert.
6. Update RunCreateForm: khi template được chọn là `automation-testing-api` → set `accept=".md,.markdown"` và validate clientside trước khi POST.

## Success Criteria

- [ ] User upload `.txt` lên template `automation-testing-api` → FE chặn trước khi POST (rõ ràng).
- [ ] User upload `.md` thiếu Response section → FE hiển thị error structured kèm tên section thiếu (không phải stack trace).
- [ ] Card "Report Verification" hiển thị đúng count khi run completed.
- [ ] Button download disabled khi `verified=false`; tooltip chứa lý do (vd "Missing unit test files").
- [ ] Cypress/Playwright happy-path test pass: upload valid MD → download HTML thành công.

## Risk Assessment

- **Risk:** Admin-app + user-app drift → 2 nơi phải sync. **Mitigation:** Toàn bộ logic ở `packages/shared`; 2 app chỉ inject component.
- **Risk:** WebSocket event không expose `error_type`. **Mitigation:** Đảm bảo Phase 2 đính kèm `error_type` vào WS payload `node.failed`.

## Security Considerations

- Endpoint verification + download đều dùng `Depends(get_current_user)` (đã có pattern).
- Force-download bypass chỉ admin (`require_admin`).

## Next Steps

Phase 8 cover tests + docs cho toàn bộ flow.
