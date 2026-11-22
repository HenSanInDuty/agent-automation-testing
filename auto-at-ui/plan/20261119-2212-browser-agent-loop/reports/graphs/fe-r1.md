STATUS: DONE (hgraph check vẫn exit 1 vì lỗi repo-level, không do file graph này)

CONTEXT_CHECK
- conventions: repo không có docs/code-standards.md, docs/api-conventions.md (hgraph brief báo thiếu)
- graphs: vision-dashboard (đích), vision-exploration (related, không sửa)
- blast radius: 24 file ngoài graph gọi vào, 9 file ngoài graph bị gọi (từ vùng auto)

## Việc đã làm
Điền 3 mục ngoài vùng auto trong `docs/graphs/vision-dashboard.md`; vùng `<!-- hgraph:begin auto -->` giữ nguyên. Không sửa file nào khác.
Nguồn đã đọc: vision-dashboard.tsx, vision-session-detail.tsx, vision-live-screen.tsx, vision-operation-model.ts, vision-operation-ledger.tsx, vision-provider-model.ts, vision-provider-settings.tsx, generation-api.ts, api-client.ts, generation-dashboard.tsx, generation-types.ts, apps/control-plane/api/v1/routes/vision.py, apps/dashboard/package.json.

## Phát hiện
- generation-dashboard.tsx mount VisionDashboard (:143) và import chung generation-types.ts; không có vòng phụ thuộc (đã bỏ một câu ban đầu ghi nhầm là vòng).
- Component .tsx của Vision không có unit test riêng; chỉ model/api có test (*.test.ts), UI được phủ bởi Playwright workers/playwright/src/vision-dashboard.spec.ts.
- Mục 2 hơi dài (8 bước, vượt ~15 dòng nếu tính theo dòng hiển thị) vì cần dẫn file:line cho từng bước.

## hgraph check (output thật)
```
hgraph check — 4 graph, 437 file source

✖ [conventions] repo không có docs/code-standards.md hay docs/api-conventions.md

Cách xử lý:  drift/stale-file → `hgraph sync <slug> --apply`
             uncovered-changed → `hgraph add <slug> <file...>` hoặc lập graph mới bằng /h-graph
```
Lỗi duy nhất là thiếu file convention của repo (có từ trước, ngoài phạm vi). Không có drift/stale-file/uncovered với vision-dashboard.

CONVENTION_ISSUE
- file: docs/code-standards.md, docs/api-conventions.md
- vấn đề: không tồn tại trong repo, làm hgraph check fail ở mục [conventions]
- tôi cần làm gì: không cần cho nhiệm vụ này; leader/user quyết định có tạo hai file không

GRAPH_UPDATE
- graph đã cập nhật: vision-dashboard (chỉ phần mô tả người viết)
- file mới đã đưa vào graph: không có
- hgraph check: xem trên (exit 1 do thiếu convention, không phải do graph)
