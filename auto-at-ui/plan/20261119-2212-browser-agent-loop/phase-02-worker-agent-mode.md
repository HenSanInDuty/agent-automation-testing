---
phase: 2
title: "Worker agent mode"
status: pending
priority: P1
owner: be-developer
qa: required
dependencies: [1]
---
## Mục tiêu
Worker Playwright hỗ trợ agent mode (bật qua `VisualWorkerOpen.agent_mode`), mọi thay đổi nằm sau cờ này để v4 giữ nguyên:
chỉ snapshot mới nhất, đi tiếp tuần tự không đếm hop/state, back/navigate cho purpose explore, allowlist theo K3,
chặn hành động nhạy cảm, re-baseline form trong batch, dialog/download hồi phục được theo K4.

## Database Impact
Không đụng (worker giữ state trong RAM).

## File liên quan
Sửa:
- `workers/playwright/src/vision-operations.ts`
- `workers/playwright/src/vision-dom.ts`
Tạo:
- `workers/playwright/src/vision-agent-mode.spec.ts`
- `workers/playwright/src/fixtures/agent-loop-target.ts`

## Luồng dữ liệu của phase này
`open(agent_mode, blocked_action_terms, allowed_origins)` → session RAM có `agentMode`, `blockedTerms`, `latestSnapshotId`.
`observe_dom` → evict + dispose snapshot cũ → trả elements + `skipped_count` (đã có).
`prepare(dom_snapshot_id, dom_element_id)` → (agent) reject `stale_dom_snapshot` nếu snapshot ≠ latest → ground →
chặn submit/download/keyword/ngoài allowlist → before frame. `execute` → action → settle → after frame → (agent) re-baseline
`snapshot.state` khi chỉ `privateForms` đổi do chính action.

## Convention áp dụng
`AGENTS.md`: TypeScript chỉ cho dashboard + worker; contract sinh từ Python (không sửa tay `vision-contract.generated.ts`).
Bám khuôn spec `vision-operations.spec.ts:20-50` (beforeEach/command/executeCommand/run).

## Graph liên quan
hgraph không index `workers/playwright/src`. Sau phase: `/h-graph` lập `playwright-vision-worker` (vision-operations,
vision-dom, vision-checkpoints, vision-history, vision-http, vision-contract) — user chọn thời điểm.

## Các bước thực hiện
1. Session: lưu `agentMode`, `blockedTerms`; `latestSnapshotId` cập nhật ở `observeDom` (vision-operations.ts ~:281-289);
   agent mode: xoá snapshot cũ khỏi `domSnapshots` và dispose `anonymousTargets` handle; bỏ chặn `dom_snapshot_limit` (:279) vì luôn ≤ 1.
2. `prepare` (~:488-495): agent mode → `dom_snapshot_id !== latestSnapshotId` ⇒ `stale_dom_snapshot` (đã có mã, không thêm action).
3. Guard tuần tự (agent mode): không push ancestry/không tăng `exploredStates` cho op explore (:504-505, :665, :803);
   cho `back` và `navigate` (về target_url) với purpose `explore` (:523-528).
4. Allowlist (K3): trong `context.route("**/*")` (:138) chỉ ghi nhận như cũ (không abort sub-resource); khi top-level
   document của page/popup ngoài `allowed_origins` (dùng `allowedOrigin`, vision-contract.ts:178) → đánh dấu page "observe-only";
   `prepare` trên page observe-only với kind ≠ `close_popup`/`back` ⇒ `rejected` mã `origin_blocked`. Click `<a href>` tới origin
   ngoài allowlist mở popup bình thường (để quan sát) — không chặn.
5. Hành động nhạy cảm (agent mode), sau ground cạnh `out_of_scope_target` (:557): `el.type in {submit,reset}`; nút submit của
   `form` (button không có `type` trong form); `a[download]`; tên/role khớp `blocked_action_terms` nhận từ `VisualWorkerOpen`
   (so khớp sau chuẩn hoá NFC + chữ thường; worker không giữ danh sách riêng) ⇒ `rejected` mã `sensitive_action_blocked`.
6. Re-baseline form (agent mode): sau `type` thành công mà URL + interaction fingerprint không đổi, cập nhật `snapshot.state`
   theo `session.state` để action kế trong batch không bị `stale_dom_snapshot` vì `privateForms` (vision-dom.ts:249; checkpoints.ts:147).
7. Dialog/download (K4, agent mode): dialog bị dismiss và download bị cancel trong lúc op đang chạy → outcome code giữ nguyên
   (`dialog_unsupported`, `download_started`) nhưng KHÔNG set `policyFailure` vĩnh viễn; ngoài op đang chạy hoặc `action_outcome_unknown` → giữ như v4.
8. Fixture `agent-loop-target.ts` (server loopback tĩnh, không mạng ngoài): form 3 ô + nút submit + nút không `type`, link ra
   origin khác (popup, mở bằng origin loopback thứ hai), ảnh tải từ origin khác, link `download`, nút gây `confirm()`, `alert()`,
   `prompt()`, trang có `beforeunload`, nút đổi nội dung tại chỗ, link điều hướng cùng origin, nút "Xoá tài khoản", "XOÁ" (NFD),
   "ĐĂNG KÝ", "NẠP THẺ".
(Marker trimmed dùng `skipped_count` có sẵn — `vision-dom.ts` không cần đổi field; chỉ sửa nếu bước 1 cần.)

## Unit test phải viết
`vision-agent-mode.spec.ts` (Chromium thật, `--workers=1`; mỗi spec mới chạy 3 lần liên tiếp xanh để loại flaky):
- snapshot cũ bị evict: prepare bằng snapshot trước ⇒ `stale_dom_snapshot`, không click (kiểm DOM fixture không đổi).
- Mở session với `max_states`/`max_hops` nhỏ (ghi giá trị trong test, ví dụ 3/2) rồi 25 observe + 25 click explore liên tiếp:
  không `dom_snapshot_limit`, không `hop_limit`/`state_limit`; handle cũ đã dispose. Cùng cấu hình ở v4 mode chạm limit (đối chứng).
- back/navigate purpose explore chạy ở agent mode; ở v4 mode giữ hành vi cũ.
- popup ngoài allowlist mở được; click trong popup ⇒ `origin_blocked`; `close_popup` chạy; ảnh từ origin khác vẫn tải (sub-resource không bị chặn).
- submit / nút không `type` trong form / `a[download]` / "Xoá tài khoản" / "XOÁ" (NFD) ⇒ `sensitive_action_blocked`, không có request
  submit; "ĐĂNG KÝ", "NẠP THẺ" KHÔNG bị chặn; `type` vào ô form không submit form.
- batch `type A` rồi `type B` cùng snapshot chạy cả hai.
- `confirm()`, `alert()`, `prompt()`, `beforeunload` do click ⇒ outcome báo về, session còn dùng được; download do click bị cancel
  và op kế chạy được; download ngoài op và `action_outcome_unknown` vẫn khoá session như v4; v4 mode khoá như cũ với mọi trường hợp.

## Tiêu chí xong (checklist)
- [ ] `npm.cmd run typecheck`, `npm.cmd run lint` sạch.
- [ ] `vision-agent-mode.spec.ts` xanh.
- [ ] Hồi quy xanh: `vision-operations`, `vision-dom`, `vision-history`, `vision-locators`, `vision-target-preflight`,
      `vision-visual-buttons`, `vision-readiness`, `vision-outcome-capture`, `contract` spec (`--workers=1`).
- [ ] v4 không đổi: các spec hồi quy trên chạy với `agent_mode=false` xanh, không sửa spec v4 nào.

## Rủi ro & tín hiệu nhận biết hỏng
- Nhánh agent rò sang v4 → spec v4 đỏ hoặc benchmark v4 đổi số operation.
- Dispose handle khi op đang dùng → lỗi `Target closed`/`stale_locator` bất thường trong spec batch.
- Từ khoá nhạy cảm chặn nhầm control mongchiton (ví dụ "ĐĂNG KÝ", "NẠP THẺ" là link mở popup, KHÔNG được nằm trong danh sách) →
  phase 6 thấy `sensitive_action_blocked` trên target oracle.
