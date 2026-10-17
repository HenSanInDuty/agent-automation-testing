# Phase 04 — Chọn Gehihi trên dashboard

## Execution status

Completed: 2026-10-17 18:47 +07:00 (started 18:37 +07:00).
Provider settings, saved/draft separation, provider-bound consent, frozen submit
confirmation and stale recovery, session labels and safe failures implemented.
Dashboard typecheck/build, worker typecheck, 31 unit tests and 10 real browser
fixture tests passed without skips. Initial select-label failures were fixed.
The shared API client and API tests additionally preserve structured safe codes.
See the canonical README for exact paths, commands, warnings and phase 05 handoff.

## Mục tiêu / prerequisites

Sau API phase 01 và integration phase 03, tenant admin cấu hình provider, người chạy biết chính xác bên nhận screenshot, và lỗi không còn chỉ là agent đứng im. Tuân thủ component/style/CSRF conventions hiện tại.

## Files

Sửa:
- `apps/dashboard/app/vision-dashboard.tsx`.
- `apps/dashboard/app/generation-types.ts`.
- `apps/dashboard/app/generation-api.ts`.
- `apps/dashboard/app/components/vision-result-summary.tsx`.
- `workers/playwright/src/vision-dashboard.spec.ts`.

Thêm:
- `apps/dashboard/app/components/vision-provider-settings.tsx` — form cấu hình nhỏ.
- `apps/dashboard/app/components/vision-provider-model.ts` — helpers thuần cho label/form transition/confirmation.
- `apps/dashboard/app/components/vision-provider-model.test.ts`.

`apps/dashboard/app/components/vision-session-detail.tsx` chỉ sửa nếu cần đặt snapshot label hoặc error context; giữ polling/trace presentation.

## UX và data flow

1. Fetch catalogue và saved policy bằng API client hiện có. Thêm types/API helper cho provider list và consent binding; không hard-code hai danh sách model ở nhiều nơi. Nếu catalogue lỗi, báo tải cấu hình thất bại và cho retry; không âm thầm chọn provider khác.
2. Tách `savedPolicy` với `draftPolicy`. Dropdown chỉ chỉnh draft. Lưu thành công mới thay saved; lỗi vẫn giữ draft để sửa và saved để phản ánh server. Chặn mở xác nhận chạy khi có thay đổi chưa lưu, hướng dẫn lưu hoặc hủy thay đổi.
3. Tenant admin có provider dropdown và model control. Gehihi cho model đã chốt; HF bảo toàn custom model đang lưu theo validation server. User khác đọc cấu hình, không chỉnh; server vẫn là nơi enforce quyền.
4. Chọn provider khác: reset consent false/binding null và đặt enabled=false để draft hợp lệ, chọn model phù hợp provider mới. Không kéo tên model HF sang Gemini. Cần xác nhận lại trước enable/save. Đổi model cùng provider không cần consent recipient mới.
5. Hiển thị thiếu key từ configured=false; không có ô nhập/show API key trong dashboard. Chỉ dẫn ngắn “Gehihi chưa được cấu hình trên máy chủ”, không lộ env/stack trace vào user flow.
6. Policy checkbox, note trước run và ConfirmDialog dùng tên recipient từ saved policy. Nội dung rõ ảnh chụp sẽ gửi đến Google, free-tier có điều kiện sử dụng dữ liệu; không gọi ảnh đã được anonymized. Mọi chỗ hard-code Hugging Face trong consent được thay bằng label phù hợp.
7. ConfirmDialog freeze provider/model của saved policy khi mở; gửi `expected_provider`/`expected_model` từ snapshot đó. 409 vision_policy_changed: đóng confirmation, tải lại saved policy, yêu cầu xác nhận mới; không auto-resubmit.
8. Session detail dùng provider/model trong session response, không dùng tenant current policy. Nhãn “Gehihi (Google Gemini)” áp dụng ID gemini, unknown ID lịch sử hiển thị an toàn.
9. Map safe reasons: chưa cấu hình, key/quyền bị từ chối, billing required, quota/rate limit, model unavailable, timeout, invalid output và policy revoked. Giữ support legacy model_unavailable + Drive auth reason. Không render body provider hoặc khuyến nghị tự bật billing.
10. Trace partial và action trước lỗi vẫn xem được. Phân biệt exploration result với draft generation result; không nói đã kiểm tra toàn bộ nút vì model trả stop hoặc step limit. Không thay đổi screenshot polling thành video/live stream.

## Tests / commands

Helpers tests chỉ kiểm chứng behavior quan trọng: provider switch reset consent/model, unsaved/save failure không thay saved recipient, unknown labels, stale confirmation dùng snapshot. Browser fixtures kiểm tra admin/nonadmin, save/reload, missing key, provider/model selection, confirmation payload, 409 refresh, legacy HF và session label độc lập current policy.

```powershell
pnpm --filter @auto-at/dashboard typecheck
pnpm --filter @auto-at/dashboard test
pnpm --filter @auto-at/dashboard build
pnpm --filter @auto-at/playwright-worker test src/vision-dashboard.spec.ts
```

Đặt `VISION_DASHBOARD_URL` cho process test tới dashboard fixture local theo runbook. Test file tự skip khi thiếu biến; phải chạy các scenario thật trước đánh dấu done. Mock backend/provider, không dùng key hoặc target thật.

## API/schema / exit criteria / risks

TS types theo API phases 01/03, không schema DB/worker change. Reload giữ provider/model/consent, UI và server không lệch recipient, nonadmin không sửa được. Accessibility: label/select/checkbox/keyboard navigation theo component hiện có. Không generic settings redesign, key management UI hoặc real-time screen streaming.
