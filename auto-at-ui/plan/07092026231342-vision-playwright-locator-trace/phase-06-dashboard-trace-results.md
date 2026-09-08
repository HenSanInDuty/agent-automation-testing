# Phase 6 — Dashboard theo dõi Vision và xem kết quả

Trạng thái: completed. Phụ thuộc: Phase 5 APIs; synthetic fixtures có trước khi chạy real session.

## Source thêm/sửa

Sửa:
- `apps/dashboard/app/vision-dashboard.tsx`
- `apps/dashboard/app/generation-api.ts`
- `apps/dashboard/app/generation-types.ts`
- `apps/dashboard/app/generation-dashboard.tsx`
- `apps/dashboard/app/components/vision-trajectory.tsx`
- `apps/dashboard/app/components/vision-replay-model.ts`
- `apps/dashboard/app/components/vision-progress-timeline.tsx`
- `apps/dashboard/app/components/vision-progress-timeline-model.ts`
- `apps/dashboard/app/components/fixtures/vision-trajectory.ts`
- `apps/dashboard/app/globals.css`

Thêm:
- `apps/dashboard/app/components/vision-operation-ledger.tsx`
- `apps/dashboard/app/components/vision-locator-catalog.tsx`
- `apps/dashboard/app/components/vision-result-summary.tsx`
- `workers/playwright/src/vision-dashboard.spec.ts` — browser integration dùng API fixtures; chạy khi dashboard test server có sẵn, không đặt React test lib mới nếu chưa cần.

## Giao diện và hành vi

1. Khi View một session, ưu tiên nội dung session được chọn: tóm tắt kết quả → trace → locators/branches; form tạo phiên và settings có thể thu gọn. Hiện selected ID rõ và hỗ trợ `/agent?vision=<session_id>` để mở lại.
2. Trace mặc định là chronological ledger mọi operation thực tế. Mỗi hàng: action, element safe label, verified/unresolved locator, status, thời điểm, before → after. Setup/back/restore/replay có nhãn riêng; collapse phục hồi nhưng không bỏ dấu vết.
3. Branch view là điều hướng bằng chứng đã lưu. Chọn sibling phải đổi selected path và frame đồng bộ, kể cả sibling ngoài default path. Đưa terminal child/failed/missing frame vào view thích hợp. Cycle guard cho dữ liệu bất thường.
4. Một marker cho action được chọn trên before tương ứng. Giữ normalized coordinate fix đã có; không overlay tất cả proposal trên gallery như thể đều đã execute.
5. Bỏ copy gây hiểu nhầm “Use this as current state”: xem frame chỉ là chọn ảnh lịch sử, không điều khiển browser. Dùng “View this frame”. State worker live hiển thị riêng theo observation mới nhất.
6. Live follow toggle: theo frame mới khi bật; user scrub thì giữ selection khi polling/SSE cập nhật. Stable operation IDs, không reset step vì object trajectory mới.
7. Refresh trace/frame/result nhất quán theo revision từ activity và fallback poll. Guard/abort request cũ khi đổi session/project/API URL; không lẫn data hai session. Fetch errors/deleted/forbidden hiển thị riêng, không loading vô hạn.
8. `VisionProgressTimeline` dừng stream/poll khi session terminal; còn generation/run/report đang pending thì poll result có điều kiện độc lập. Cleanup timers, blob object URLs và fetch đang bay khi unmount/chọn khác/xoá.
9. Kết quả có các trạng thái đọc được: “Khám phá hoàn tất”, “Locator đã xác minh”, “Không đủ bằng chứng”, “Tạo draft thất bại”, “Chờ duyệt”, “Đang chạy test”, “Xem kết quả Playwright”. Render literal copy theo ngôn ngữ UI hiện có; không trộn implementation jargon vào luồng chính.
10. Link dùng explicit IDs từ result: draft `/agent?draft=...`, run `/runs/...`; summary và JSON export hiện trên màn Vision kể cả không có run. Draft UI hiển thị provenance nguồn Vision và link trace.
11. Mỗi ảnh trước/sau load độc lập; một ảnh lỗi không làm mất ảnh còn lại. Gallery pagination/lazy fetch, không tải hết ảnh private trước.
12. Keyboard chỉ khi trace panel được focus; arrow/home/end không chiếm bàn phím trong input/textarea/select. Focus/aria current/alt/status đủ rõ và layout responsive.

## Tests và validation

Sửa `generation-api.test.ts`, `generation-dashboard.test.ts`, `components/vision-replay-model.test.ts`, `components/vision-progress-timeline-model.test.ts`.
Thêm `components/vision-operation-model.test.ts` nếu tách selector thuần, và browser spec ở worker như trên.
Browser test phải click sibling, scrub qua polling update, đổi session khi response cũ trễ, simulate image 404, live frames, report failure và thao tác keyboard input. Không chỉ source-text assertions.

Tại `apps/dashboard/`:
```text
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
```
Tại `workers/playwright/`, với local dashboard fixture server:
```text
npm.cmd test -- src/vision-dashboard.spec.ts
```

## Nghiệm thu và non-goals

User xem được agent đã làm gì/locator gì/khôi phục ra sao và tìm được kết quả sau refresh. Completed exploration nhưng generation failure hiển thị ngay, không ngụ ý test passed. Không thêm remote browser control, video generator hoặc approval step mới.


## Phase 6 completion ? 2026-09-08 23:25 +07:00

Status: **completed**. Selected-session results precede collapsed creation/settings. Added the chronological operation ledger, immutable branch navigation, before/after frames with independent error states, locator catalog, safe JSON export and explicit downstream links. Stable operation IDs survive polling; follow mode is optional. Deep links, stale-response guards, abortable image requests, object URL cleanup, terminal progress cleanup and conditional downstream polling are implemented. Legacy sibling selection now rebuilds the path with cycle guards; historical frame selection says ?View this frame?. Keyboard navigation is confined to the focused trace and ignores form controls.

Validation: dashboard typecheck passed; dashboard unit/API tests **27 passed**; three intercepted-API Chromium dashboard scenarios **3 passed** (13.4s), including delayed session switches, image 404 with retained before image, polling/follow/keyboard, deep links and the legacy seven-frame/six-sibling case. Worker typecheck passed with the browser fixture. Production `npm.cmd run build` passed with all nine pages generated; existing workspace-root and ESLint-plugin configuration warnings remain. The first build found two unused variables; fixed the legacy compatibility argument and wired independent frame error copy, then rebuilt successfully. No provider calls.

Changed paths: `apps/dashboard/app/{vision-dashboard.tsx,generation-api.ts,generation-api.test.ts,generation-types.ts,generation-dashboard.tsx,globals.css}`; `apps/dashboard/app/components/{vision-operation-ledger.tsx,vision-operation-model.ts,vision-operation-model.test.ts,vision-locator-catalog.tsx,vision-result-summary.tsx,vision-session-detail.tsx,vision-trajectory.tsx,vision-replay-model.ts,vision-replay-model.test.ts,vision-progress-timeline.tsx,vision-progress-timeline-model.ts,fixtures/vision-trajectory.ts}`; `workers/playwright/src/vision-dashboard.spec.ts`.

Deviations: no React test dependency was added; behavior is covered by existing Node tests and actual Chromium. Polling uses revision-aware metadata requests and fetches only selected frame bytes. The new session-detail component isolates request ownership. Phase 7 is unlocked; production deployment and real-provider canary have not run.
