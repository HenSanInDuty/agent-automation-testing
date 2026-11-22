---
phase: 5
title: "Dashboard"
status: completed
priority: P2
owner: fe-developer-junior
qa: required
dependencies: [1, 4]
---
## Mục tiêu
Cho người dùng chọn engine khi tạo exploration và xem suy luận từng bước của agent loop trong ledger có sẵn, không thêm file/component mới.

## Database Impact
Không đụng.

## File liên quan
Sửa:
- `apps/dashboard/app/generation-api.ts` (~:48: payload thêm `engine`)
- `apps/dashboard/app/vision-dashboard.tsx` (~:22, :178, :243-255: state + `<select id="vision-engine">` Planner/Agent loop; chỉ hiện khi
  `agent_loop_enabled` của response vision policy (phase 1) là true; nhãn "advisory, model proposals only" đổi cho session agent loop)
- `workers/playwright/src/vision-dashboard.spec.ts` (spec dashboard sẵn có trong package worker; thêm case e2e với API mock)
- `apps/dashboard/app/generation-types.ts` (~:155: `engine?` trên session, `agent_step?` tuỳ chọn trên `VisualOperation`)
- `apps/dashboard/app/components/vision-operation-ledger.tsx` (~:30: khối "Đánh giá bước trước / Memory / Mục tiêu kế" khi có `agent_step`; dòng "blocked" kèm lý do)
- `apps/dashboard/app/components/vision-provider-model.ts` (~:100: câu hiển thị cho `stale_ref`, `origin_blocked`, `sensitive_action_blocked`, `agent_step_limit`, `agent_done`, `agent_stopped`)
- Test cạnh file: `vision-provider-model.test.ts` (đã có) + test cho mapping/format mới.

## Luồng dữ liệu của phase này
Form → `generation-api` `POST /explorations {..., engine}` → response `engine`. Chi tiết session poll `/trace` (5 s) → `VisualOperation.agent_step?` → ledger.
Phụ thuộc: phase 4 đưa `agent_step` tuỳ chọn vào trace payload (`vision_results.py`); field vắng thì UI không hiện khối.

## Convention áp dụng
`AGENTS.md`: TypeScript chỉ dashboard + worker. Repo không có convention UI riêng → bám pattern `vision-dashboard.tsx`/ledger hiện có;
test `node:test` `*.test.ts`. Giữ gating `trace_version === "v4"` (session agent loop vẫn v4).

## Graph liên quan
Không graph dashboard. Không bắt buộc lập mới.

## Các bước thực hiện
1. Types + API payload.
2. Select engine (id ổn định, label rõ, mặc định Planner).
3. Ledger hiển thị `agent_step` và dòng blocked.
4. Map mã lỗi mới.
5. Test + typecheck + lint.

## Unit test phải viết
- Mapping mã lỗi mới ra câu hiển thị (không rơi vào thông báo chung).
- Hàm format/chọn dữ liệu `agent_step` cho ledger (có/không có field).
- Payload tạo exploration có `engine` khi chọn Agent loop, không có (hoặc `planner`) khi mặc định.
- Fallback: mã lỗi chưa biết, `agent_step` rỗng hoặc rất dài (cắt/xuống dòng, không tràn), tiếng Việt có dấu, `engine` lạ hiển thị như planner.
- E2E (`vision-dashboard.spec.ts`, API mock): `agent_loop_enabled=false` ⇒ không có select; true ⇒ có select, gửi `engine`; ledger session agent
  hiện 3 trường + dòng blocked; session planner không có khối agent; viewport 400px: `document.documentElement.scrollWidth <= innerWidth`.

## Tiêu chí xong (checklist)
- [ ] `pnpm --filter @auto-at/dashboard test`, `typecheck`, `lint` xanh.
- [ ] Session planner hiển thị y như trước (không khối agent_step) — chứng minh bằng e2e.
- [ ] E2E `vision-dashboard.spec.ts` xanh (`--workers=1`).

## Rủi ro & tín hiệu nhận biết hỏng
- Đổi `trace_version` hoặc gating ⇒ session rơi vào nhánh legacy (UI mất timeline).
- Lỗi encoding có sẵn ở `vision-conclusion.tsx` (chuỗi tiếng Việt hiện `?`) — ngoài phạm vi, không sửa ở phase này; ghi lại nếu thấy.
