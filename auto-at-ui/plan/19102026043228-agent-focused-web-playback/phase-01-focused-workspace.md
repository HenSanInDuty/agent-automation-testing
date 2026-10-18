# Phase 01 — Workspace tập trung vào thao tác website

Status: **completed** — started 2026-10-19 04:37, completed 04:44 +07:00.

Implementation/changed paths, exact validation results and deviations are recorded in the canonical README execution log. Viewer/steps, disclosure layout, scoped policy and draft deep-link/approval regression are implemented. 33 unit tests and all 23 browser cases passed across the recorded runs; typecheck/lint passed. No backend changes. Click metadata/highlight remains phases 02/03.

## Mục tiêu, phạm vi, prerequisites

Giảm thông tin mặc định trên /agent, đưa website và diễn biến thực thi lên đầu. Phase độc lập, dùng API hiện có và chưa phụ thuộc click metadata.

Trước khi sửa: đọc README kế hoạch, git status/diff hiện tại; giữ các thay đổi uncommitted về screen/reload/report. Đọc các components/tests được liệt kê dưới đây.

## File cần sửa/thêm

- Sửa `apps/dashboard/app/generation-dashboard.tsx`: chọn tab theo route, compact header, project settings theo project Vision đang chọn.
- Sửa `apps/dashboard/app/vision-dashboard.tsx`: toolbar, form theo trạng thái, history/settings disclosure, đưa selected session lên trước.
- Sửa `apps/dashboard/app/components/vision-session-detail.tsx`: một nguồn selected/follow; bố cục viewer + steps; vùng details đóng mặc định.
- Sửa `apps/dashboard/app/components/vision-live-screen.tsx`: hỗ trợ selected operation và before/after, vẫn dùng preview cũ khi follow.
- Sửa `apps/dashboard/app/components/vision-operation-ledger.tsx`, `vision-operation-model.ts`: compact list, nhãn thân thiện, chi tiết kỹ thuật tách khỏi danh sách.
- Sửa `apps/dashboard/app/components/vision-result-summary.tsx`: summary ngắn và detailed report mở khi cần.
- Sửa `apps/dashboard/app/components/vision-progress-timeline.tsx`: duy trì subscription khi nội dung kỹ thuật đóng; tránh mount hai timeline.
- Sửa `apps/dashboard/app/globals.css`: layout, image surface, responsive, focus states.
- Sửa `apps/dashboard/app/components/vision-operation-model.test.ts` và `workers/playwright/src/vision-dashboard.spec.ts`; thêm `apps/dashboard/app/components/agent-workspace-model.ts` và `agent-workspace-model.test.ts` nếu tách helper chọn tab theo query.

Các đường dẫn rút gọn trên đều thuộc `apps/dashboard/app/components/`.

## Hành vi và data flow

1. /agent không có deep link mở Vision. draft query mở review; vision query chọn đúng session; draft ưu tiên khi cả hai cùng có. Chuyển query trên cùng page phải cập nhật tab, không chỉ lần mount.
2. Không có phiên: hiện Project/URL/Intent. Có phiên: toolbar hiện trạng thái, New, History, Reload; form tạo mới đóng. Không auto-submit hay thay provider khi chọn tab.
3. Form New vẫn giữ disclosure và confirmation hiện tại. Thiếu policy/consent hiện một thông báo gọn cùng đường mở Settings; settings lỗi/dirty không bị che khi submit bị khóa. Giữ bản nháp form khi đóng/mở.
4. History là disclosure hoặc panel gọn; chọn phiên cập nhật URL hiện có và reset selection/frame/follow phù hợp. Không dùng UUID dài làm nội dung chính; dùng trạng thái và thứ tự/tên phiên có dữ liệu, ID ở details.
5. Website chiếm khoảng 2/3 desktop, danh sách bước khoảng 1/3. Dùng cùng trace cho list và viewer. Chọn bước tắt follow và tải before/after bằng getOperationFrameBlob; không gửi lệnh worker. Khi follow và active, getVisionScreen vẫn cung cấp ảnh live.
6. Nhãn bước là phép ánh xạ deterministic từ action_kind, status và safe descriptor/report target. Ví dụ “Click ‘Open details’”, “Scroll page”, “Go back”; rejected là “Not executed”, unknown là “Outcome unknown”. Không hiển thị typed input hoặc raw locator làm nhãn mặc định.
7. Giữ mọi bước theo sequence, kể cả restore/replay nhưng nhãn dễ hiểu; branch/filter chi tiết có thể chuyển vào disclosure. Chọn before/after hiển thị role rõ, ảnh thiếu/xóa có trạng thái riêng; không tráo bằng ảnh của bước khác.
8. Kết quả mặc định: trạng thái exploration, số thao tác có bằng chứng, lý do dừng và link Review draft/View run khi tồn tại. Report dài, raw counts, provenance, locator, correlation, budget, logs và JSON export nằm trong details. Link “View exploration report” phải mở disclosure rồi đưa report vào vùng nhìn thấy.
9. Giữ một bộ subscription progress kể cả logs đóng để onActivity cập nhật session. Dùng lifecycle session như hiện tại; đừng unmount progress rồi làm phiên active đứng yên.
10. Project policy phải dùng project của Vision đang chọn, không project mặc định của generation tab. Tách callback/context hoặc truyền project ID có kiểu thay cho ReactNode gắn state cũ; không gửi save cho project khác.
11. RBAC và dialog xóa evidence giữ nguyên, thao tác xóa trong details; việc thu gọn không làm quyền rộng hơn. Legacy evidence vẫn đọc được trong phần tương ứng, marker proposal giữ nhãn proposal.
12. Dùng semantic button/details, keyboard focus, aria-current cho bước; không làm mất focus mỗi lần polling. Trên mobile stack ảnh trước list.

## API/schema

Không đổi API hoặc persistence. Tái sử dụng getVisualTrace đã ghép trang và xử lý revision 409. Không thay code route /agent hoặc auth nếu không cần.

## Tests và validation

- Unit: tab/deep link precedence, selected/follow khi trace append, label không biến rejected/unknown thành success.
- Browser fixture: selected session ở đầu; form New/history/settings mở được; Project B settings không ghi vào A; deep links; consent/dirty policy/reload; partial failure và legacy vẫn xem được.
- Before/after thay đúng ảnh khi chọn operation; phản hồi phiên cũ đến trễ không đổi ảnh hiện tại; đóng details không dừng progress.
- Viewport 1440×900 và 390×844; keyboard/focus; report link mở đúng nội dung.

```powershell
pnpm --filter @auto-at/dashboard test
pnpm --filter @auto-at/dashboard typecheck
pnpm --filter @auto-at/dashboard lint
$env:VISION_DASHBOARD_URL = 'http://localhost:3000'
pnpm --filter @auto-at/playwright-worker test src/vision-dashboard.spec.ts
```

Browser tests cần dashboard chạy đúng source mới; fixture mock API trước navigation. Không kết luận pass nếu toàn bộ suite skip vì thiếu VISION_DASHBOARD_URL.

## Acceptance, rủi ro, non-goals

- Đạt tiêu chí README 1–3 và 8; chọn bước đổi đúng ảnh dù chưa có marker.
- Report/config vẫn truy cập được, lỗi quan trọng và consent không bị giấu.
- Rủi ro: component chung ảnh hưởng generation; chạy lại deep link draft và approval fixture. Chỉ cập nhật assertion layout đã đổi có chủ đích, giữ assertion quyền/consent.
- Không thay agent, endpoint, runner, evidence schema hoặc tạo framework design system mới.
