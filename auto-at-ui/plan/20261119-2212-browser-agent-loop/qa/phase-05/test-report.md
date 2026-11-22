QA VERDICT: PASS (phạm vi phase 5; xem cảnh báo hgraph bên dưới)

# Phase 5 (Dashboard) - Test report

## Môi trường
Windows 11, Node v24.12.0, nhánh mantaray, working tree có thay đổi chưa commit của các phase khác. `pnpm` không có trong PATH nên chạy trực tiếp đúng lệnh của script: `node --experimental-strip-types --test`, `tsc --noEmit`, `eslint .` (cùng nội dung script package.json). E2E: `next build` rồi `next start` cổng 3107 + `playwright test src/vision-dashboard.spec.ts --workers=1` (wrapper foreground có timeout, tự dừng server).

## Kết quả (output thật)
- Unit: `ℹ tests 49 / pass 49 / fail 0` (48 của dev + 1 case QA thêm).
- typecheck: exit 0. lint: exit 0. build: exit 0.
- E2E working tree: `2 failed ... 55 passed (1.7m)`; 2 đỏ là spec:238 và spec:336, cùng lỗi `toBeInViewport ... Received: viewport ratio 0`. Ba e2e mới của phase đều xanh.
- E2E BASELINE (git worktree ở HEAD f85091a, node_modules nối bằng junction, build riêng, chỉ chạy 2 test đó): `2 failed` - spec:236 "Vision cards align on desktop..." và spec:334 "a saved session focuses the website..." (số dòng lệch 2 vì spec của phase thêm 2 dòng fixture), cùng lỗi `Timed out 5000ms waiting for expect(locator).toBeInViewport() ... Received: viewport ratio 0`.
  => Kết luận: cả hai đỏ SẴN CÓ ở baseline, không phải hồi quy của phase 5. Nên xử lý riêng (nghi: `toBeInViewport` với viewport/scroll của môi trường này).
- Worktree đã gỡ (`git worktree list` chỉ còn repo chính + worktree admin-ui-rework có sẵn); junction đã gỡ trước khi remove nên node_modules thật còn nguyên; cổng 3107 không còn listener (chỉ TIME_WAIT).

## Coverage
Xem test-cases.md (18 case; 16 PASS, 2 đỏ sẵn có ở baseline). Phủ: gating select, payload engine, 3 trường + dòng blocked, planner không đổi, 10 mã lỗi, fallback dài/rỗng/tiếng Việt/engine lạ/dữ liệu sai kiểu, viewport 400px.
Automation QA thêm: 1 unit test cuối `vision-provider-model.test.ts` ("QA: agent step view tolerates malformed...").

## Chưa test được / ghi chú
- BE `/trace` chưa trả `agent_step` ở production (phase 4 mục 1) -> chưa có kiểm chứng end-to-end thật, chỉ API mock. Không thuộc phase 5.
- `engine` lạ trên session: chỉ có helper `explorationEngine`; UI không hiển thị nhãn engine của session nên không có thứ gì để assert ngoài unit.
- Lỗi encoding `vision-conclusion.tsx` ngoài phạm vi, không kiểm.
- Nhãn trộn Anh/Việt ("Memory", "Blocked") chờ user chốt (từ báo cáo dev).
- `workers/playwright` lint có 22 lỗi `no-explicit-any` ở file ngoài phase (theo báo cáo dev, không chạy lại).

## Cổng graph
`hgraph check --changed` vẫn exit 1: 48 file đổi, toàn bộ báo `uncovered-changed` với đường dẫn có tiền tố `auto-at-ui/` (git root là thư mục cha). Các file dashboard/spec của phase 5 thì `hgraph which` -> `vision-dashboard` và `hgraph check <6 file phase>` -> "Không có vấn đề"; graph `docs/graphs/vision-dashboard.md` có chứa `vision-provider-model.test.ts`. Đánh giá: lệch tiền tố đường dẫn của công cụ (cũng làm file đã có graph ở các phase khác bị báo), không phải lỗi phase 5. Leader cần quyết định coi đây là artifact hay chạy lại hgraph từ git root. Nếu leader áp cổng nghiêm ngặt thì verdict thành FAIL vì lý do này, không phải vì hành vi.
