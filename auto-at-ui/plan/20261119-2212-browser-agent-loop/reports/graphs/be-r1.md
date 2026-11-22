STATUS: DONE

CONTEXT_CHECK
- conventions: repo không có docs/code-standards.md hay docs/api-conventions.md (hgraph brief báo thiếu); đã đọc AGENTS.md và `~/.claude/skills/h-graph/reference/graph-format.md`
- graphs: vision-exploration, codex-bridge, playwright-vision-worker (đối tượng sửa)
- blast radius: không áp dụng, chỉ sửa tài liệu

Phạm vi: chỉ sửa 3 file `docs/graphs/{vision-exploration,codex-bridge,playwright-vision-worker}.md` (phần ngoài vùng auto, và khối `db:` ở frontmatter). Vùng auto và frontmatter `files:`/`entrypoints:` không đụng. Không sửa code sản phẩm. Database: không đụng (chỉ khai báo bảng trong frontmatter).

## Đã làm
- vision-exploration: điền 3 mục, thêm `db:` 10 bảng (đọc từ `infrastructure/persistence/models.py:106-458`).
- codex-bridge: điền 3 mục, thêm `db:` bảng `codex_bridge_jobs` (`models.py:180-228`, migration `c0d1e2f3a4b5` + `d1e2f3a4b5c6`).
- playwright-vision-worker: điền 3 mục, giữ `db: []` (worker không có bảng, phiên nằm trong RAM `vision-operations.ts:47`, ảnh tạm dưới `ARTIFACT_ROOT/vision-v4`).
- Mọi khẳng định đều dẫn `file:line` từ code đã đọc (routes/vision.py, application/vision*.py, vision_trace_events.py, repositories.py claim/_fence, codex_bridge spool/process/doctor, codex_batch.py, codex_bridge_repository.py, vision-http.ts, vision-operations.ts, ...).
- Vùng auto vẫn nguyên: mỗi file còn đúng 2 marker `hgraph:begin/end auto`, không còn placeholder "người viết điền".

## Phát hiện cần chú ý (không tự xử lý vì ngoài phạm vi)
1. File nằm trong chức năng nhưng chưa thuộc graph nào (`hgraph which` báo ✖):
   - `packages/contracts/src/auto_at/contracts/vision_worker.py` (và `vision.py`): nguồn sinh ra `vision-contract.generated.ts`.
   - `apps/control-plane/infrastructure/vision_worker.py`: client HTTP gọi worker Playwright.
   - `apps/control-plane/infrastructure/vision/codex_batch.py`, `application/codex_candidates.py`, `domain/codex_bridge.py`: phía producer của bridge.
   - Khuyến nghị: `hgraph add playwright-vision-worker apps/control-plane/infrastructure/vision_worker.py packages/contracts/src/auto_at/contracts/vision_worker.py` và `hgraph add codex-bridge apps/control-plane/infrastructure/vision/codex_batch.py apps/control-plane/application/codex_candidates.py apps/control-plane/domain/codex_bridge.py` (hoặc lập graph mới). Các file này chỉ được nhắc trong phần mô tả, chưa được đưa vào `files:` vì task cấm đổi danh sách file.
2. `hgraph check` thoát mã 1 chỉ vì repo thiếu `docs/code-standards.md`/`docs/api-conventions.md`, không có lỗi drift hay stale-file nào. `hgraph check --changed` thoát 0 nhưng liệt kê nhiều file đang sửa chưa thuộc graph (đã có từ trước, ví dụ `tests/test_vision_policy_routes.py`).
3. Chức năng khám phá có 2 bộ xử lý cho cùng một outbox event (legacy `VisionEventProcessor` và v4 `publish_vision_once`), đã ghi rõ ở mục "Vì sao" của vision-exploration.

## Output hgraph check (thật)

```
hgraph check — 4 graph, 437 file source

✖ [conventions] repo không có docs/code-standards.md hay docs/api-conventions.md

Cách xử lý:  drift/stale-file → `hgraph sync <slug> --apply`
             uncovered-changed → `hgraph add <slug> <file...>` hoặc lập graph mới bằng /h-graph
exit=1
```

`hgraph check --changed`: exit=0 (phần cuối output là danh sách file thay đổi chưa thuộc graph, ví dụ `auto-at-ui/tests/test_vision_policy_routes.py` và 3 file nữa).

GRAPH_UPDATE
- graph đã cập nhật: vision-exploration, codex-bridge, playwright-vision-worker (chỉ phần mô tả và khối `db:`)
- file mới đã đưa vào graph: không có (không tạo file code mới)
- hgraph check --changed: exit 0, xem ở trên

Tiến trình đã mở: không có. Log nhịp tim: `be-r1.md.log` cùng thư mục.
