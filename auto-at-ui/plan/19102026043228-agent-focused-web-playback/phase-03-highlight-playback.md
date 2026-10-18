# Phase 03 — Highlight và xem diễn biến thao tác

Status: **completed** — started 2026-10-19 04:52 +07:00; completed 05:10 +07:00.

## Implementation and validation result

- Added click eligibility/projection/preview helpers, unit tests and decorative overlay; integrated image-load identity, resize/letterbox projection, reduced motion and deduplicated recent-click playback in the viewer. Existing phase-01 ledger/selection wiring is reused.
- Changed paths: `apps/dashboard/app/components/vision-click-model.ts`, `vision-click-model.test.ts`, `vision-click-overlay.tsx`, `vision-live-screen.tsx`; `apps/dashboard/app/globals.css`; `workers/playwright/src/vision-dashboard.spec.ts`; `docs/vision-agent-operations.md`; validation-only maintenance in `tests/test_vision_provider_integration.py`, `benchmark/vision/gehihi/manifest.json` and `README.md`.
- Dashboard unit tests: 36 passed. Dashboard lint/typecheck, worker typecheck, repository Ruff, generated-contract parity and diff whitespace checks passed. Full dashboard browser file: 33 passed on source server 3100. Built dashboard smoke on 3000: 4 passed. Exact commands and evidence are in the canonical README execution log.
- Offline Python baseline: 630 passed, 1 stale origin-policy expectation failed, no skips. After correcting only that expectation, both legacy/v4 variants and the manifest gate passed (3 passed, 30 deselected). All 631 offline cases passed across these runs; no claim of a repeated all-green full run. Three configured-stack cases are excluded from the final offline harness.
- Production Docker builds passed and compatible API/worker/dashboard images are running locally on the original ports. No active Vision or deterministic execution was interrupted; no new migration/storage change. API health and /agent returned 200. Owned source server and fixture PostgreSQL were removed/stopped.
- Desktop/mobile screenshots inspected; marker assertions stay within 2 CSS px. Historical sessions and uncertain geometry intentionally have no marker. Existing worker lint diagnostics remain unchanged.
- Operational deviation: initial plain baseline ran configured-stack tests, leaving 2 synthetic tenants and 4 synthetic local runs; their reports are unavailable. Records were preserved and the final harness prevented configured-stack/provider access. See README for the full validation/deployment record.

## Mục tiêu, phạm vi, prerequisites

Tích hợp click evidence phase 02 vào workspace phase 01. Một viewer phục vụ follow và xem lại; highlight không bao giờ được ghép lên frame không xác định.

Prerequisites: phase 01 và 02 pass; đã có trace fixture với before/after khác nhau, điểm click đã xác minh và trường hợp thiếu metadata. Đọc lại README và diff hiện tại.

## File cần sửa/thêm

- Thêm `apps/dashboard/app/components/vision-click-model.ts` và `vision-click-model.test.ts`: eligibility, projection, dedupe và preview state helpers.
- Thêm `apps/dashboard/app/components/vision-click-overlay.tsx`: vòng tròn overlay thuần trình bày.
- Sửa `apps/dashboard/app/components/vision-live-screen.tsx`: before/after image surface, recent-click preview, lifecycle ảnh.
- Sửa `apps/dashboard/app/components/vision-session-detail.tsx`: selection/follow/operation cập nhật viewer thống nhất.
- Sửa `apps/dashboard/app/components/vision-operation-ledger.tsx`: selected state và thông báo điểm click nếu cần.
- Sửa `apps/dashboard/app/globals.css`: marker, pulse, reduced-motion, image surface.
- Sửa `workers/playwright/src/vision-dashboard.spec.ts`: fixtures ảnh thực tế và kiểm integrated behavior.
- Sửa `docs/vision-agent-operations.md`: diễn giải live preview/replay, legacy, lỗi ảnh và rollout/rollback đã kiểm.

File rút gọn ở hai bullet đầu nằm trong `apps/dashboard/app/components/`.

## Data flow và quy tắc rendering

1. State viewer phân biệt `live`, `recent-click`, `selected-before`, `selected-after`; key ảnh gồm apiUrl/sessionId/operationId/frameId/role. selected/follow do parent sở hữu, không có selection riêng lệch nhau giữa list và viewer.
2. Overlay chỉ render khi ảnh đã load thành công, là before frame khớp executed_click.before_frame_id, click evidence hợp lệ và ảnh retained. Nhãn “Click location”/“Recent click — recorded frame”; không gắn nhãn “Live” cho ảnh replay.
3. Viewer live tiếp tục polling /screen như hiện tại. Khi trace cập nhật có click confirmed mới, follow=true và phiên active: tải before frame rồi hiện highlight trong 1.2 giây kể từ ảnh load; sau đó quay về ảnh live mới nhất. Không chờ marker để worker chạy.
4. Bootstrap một phiên chỉ đặt watermark sequence, không chạy lại lịch sử animation. Mỗi operation được đánh dấu đã xét một lần kể cả lần tải ảnh thất bại. Khi nhiều click đến trong một poll, preview click mới nhất; mọi bước vẫn có trong list để xem lại, không xếp hàng animation gây trễ.
5. Click mới thay preview cũ và reset timer theo identity; click chọn bước, chuyển phiên hoặc tắt follow hủy timer. Khi bật follow lại, lấy watermark hiện tại, không chạy backlog. Phiên kết thúc không tạo vòng preview mới; giữ last saved screen hoặc selection người dùng.
6. Chọn bước bằng list/scrubber/keyboard hiển thị before; chọn After xem kết quả không overlay. Với bước không phải click, vẫn xem ảnh bình thường. Highlight static khi xem lại; pulse chỉ lúc recent-click.
7. Dùng một image surface có kích thước đúng bitmap hiển thị, đặt overlay tuyệt đối trên surface đó. Nếu vẫn dùng object-fit contain, tính scale=min(containerWidth/imageWidth, containerHeight/imageHeight) và offset letterbox.
8. Chuyển tọa độ: px=x×(viewport_width−1), py=y×(viewport_height−1); u=px/viewport_width, v=py/viewport_height. Map (u,v) vào vùng ảnh; natural image DPR không làm thay đổi tỉ lệ này. Xác minh ảnh là viewport frame đúng tỉ lệ; nếu thiếu/mâu thuẫn kích thước thì không vẽ.
9. Marker: chấm trung tâm và vòng tương phản hai lớp khoảng 28–36 CSS px, transform translate(-50%,-50%), pointer-events:none. Giữ điểm trung tâm đúng tọa độ ở mép ảnh; không clamp tâm vào trong. Không che label/control và không thêm tab stop.
10. prefers-reduced-motion bỏ animation, giữ vòng static. Screen-reader nhận tên bước/trạng thái qua text hiện hữu, không thông báo lại pulse mỗi lần poll.
11. URL blob cũ được revoke sau thay ảnh/unmount, request abort khi identity đổi; response/frame onLoad đến trễ bị bỏ. Đừng hiện marker trước khi ảnh tương ứng tải xong.
12. Mất quyền 401/403/404 xóa ảnh và marker, dừng retry như hiện tại. Lỗi tạm thời hiển thị trạng thái stale; không phát lại marker. Ảnh deleted/missing hiển thị thông báo, không thay bằng ảnh khác cùng session rồi vẽ marker.
13. Browser preview hỏng nhưng trace/saved frames còn dùng được thì vẫn xem lại bước. Terminal không còn polling /screen; downstream result polling giữ logic riêng.

## API/schema

Tái sử dụng executed_click optional từ phase 02 và getOperationFrameBlob/getVisionScreen hiện có. Không thêm endpoint, WebSocket, iframe website đích hoặc library animation. Legacy proposal marker không được đổi nhãn thành click confirmed.

## Tests và validation

Validation maintenance (2026-10-19): full baseline exposed a stale `origin_after-v4`
expectation in `tests/test_vision_provider_integration.py`. The existing v4 policy
observes origins without allowlist gating. Update only this expected result,
preserve legacy enforcement, refresh the referenced benchmark source checksum and
run both variants plus the manifest gate. This adds no product or policy behavior.

Unit tests:

- x/y hữu hạn, invalid/null/missing evidence; before ID mismatch; rejected/unknown/non-click; confirmed click có failed outcome vẫn giữ nhãn failed.
- Mapping center/corners, ảnh 1280×720 ở nhiều kích thước, DPR 2, letterbox ngang/dọc, sai aspect ratio; không dùng bbox center.
- Dedupe repeated poll, bootstrap, batch nhiều clicks, resume follow không backlog, session switch reset.

Browser fixtures:

- Thay PNG 1×1 bằng ảnh synthetic 1280×720 trước/sau khác nhau cho tests tọa độ; có điểm mốc rõ để kiểm marker trong dung sai 2 CSS px.
- Before hiển thị marker đúng; After/live frame hiện tại không mang marker của bước cũ sau navigation/popup/scroll.
- Recent-click preview 1.2 giây sau load rồi live tiếp tục; delayed blob/onLoad và aborted request không làm marker xuất hiện sai phiên.
- Resize desktop/mobile, reduced motion, keyboard selection, ảnh thiếu/xóa/403/503, stop live, reconnect/poll duplicate.
- Consent/provider confirmation, Reload, legacy, draft deep links và approval không hồi quy. Collapsed technical details không dừng cập nhật.
- Chụp local fixture screenshots desktop/mobile để review layout. Không gửi dữ liệu thật hoặc gọi provider để tạo ảnh kiểm thử.

```powershell
pnpm --filter @auto-at/dashboard test
pnpm --filter @auto-at/dashboard typecheck
pnpm --filter @auto-at/dashboard lint
$env:VISION_DASHBOARD_URL = 'http://localhost:3000'
pnpm --filter @auto-at/playwright-worker test src/vision-dashboard.spec.ts
uv run ruff check .
uv run pytest
```

Chạy baseline Python một lần cuối vì phase 02 đổi shared contract/persistence. Ghi rõ test bị skip do prerequisites; không coi skip là validation đủ. Không lặp/broaden checks sau pass nếu không có sửa đổi hoặc lỗi mới.

## Acceptance, rủi ro, non-goals

- Đạt toàn bộ tiêu chí README, có bằng chứng screenshot và tests thật sự chạy.
- Trong điều kiện fixture bình thường, click xuất hiện ở lần trace refresh thành công tiếp theo cộng thời gian tải frame; không hứa latency nhỏ hơn cadence trace hiện có.
- Người dùng luôn phân biệt ảnh đang live với ảnh bước vừa thực hiện. Unknown/rejected không bị tô thành thao tác thành công.
- Rủi ro: marker và ảnh lệch khi resize/race, thông báo aria quá nhiều, blob leak hoặc timer không hủy. Kiểm bằng fixtures có delay và session switch.
- Không quay/sửa video, không điều khiển browser từ UI, không bổ sung LLM summary, không inject marker vào website hoặc screenshot lưu trữ.
- Sau hoàn tất, cập nhật status các phase và kết quả validation trong README kế hoạch; báo rõ phần thiếu môi trường nếu có.
