STATUS: PASS
QA VERDICT: PASS

# Phase 15b — test report (QA r1)

## Môi trường
Windows 11, Kiri engine, Postgres dùng-một-lần `agent-task-fixture-postgres` (không khởi động lại / dừng). Code là working tree chưa commit.

## Kết quả (output thật)
| Lệnh | Kết quả |
|---|---|
| `uv run ruff check .` | `All checks passed!` (sau khi sửa 1 dòng dài trong file QA của tôi) |
| pytest (không DB, 5 file chính) | `172 passed, 73 skipped` — 73 skip do DB không với tới được (xem dưới) |
| pytest với shim DB: `test_agent_task_draft_routes` + `test_qa_p08_agent_task_trace` | `133 passed` (0 skip) |
| pytest với shim DB: draft_inputs, draft, qa_phase14, consistency, qa_p09, review_guards, qa_p13, agent_task_trace | `338 passed, 1 xfailed` (0 skip) |
| pytest với shim DB: dashboard_route_contracts, qa_p11, agent_task_renderer, vision_routes, qa_p12 | `210 passed, 1 xfailed` |
| `tests/test_qa_p15b_draft_inputs.py` (QA, mới) | `5 passed` |
| `apps/dashboard`: `npm run typecheck` / `npm run lint` | sạch |
| `apps/dashboard`: `npm test` | `tests 80, pass 80, fail 0` |
| Playwright `vision-dashboard.spec.ts` (wrapper tự bật/tắt dev server 3107) | `88 passed (3.8m)`; sau đó không còn LISTEN 3107 |
| `hgraph check` | `8 graph, 557 file source ✔ Không có vấn đề.` |

## Vấn đề môi trường: vì sao "DB test chạy thật" cần shim
Container Postgres đang chạy (`pg_isready` ok) nhưng cổng host `127.0.0.1:55437` KHÔNG mở được: `ConnectionRefused` khi nối, và `bind` thử trên host báo `WinError 10013` vì 55437 nằm trong dải cổng Windows bị loại trừ (`netsh interface ipv4 show excludedportrange` -> 55434-55533). Vì vậy chạy thẳng pytest vẫn skip 73 test (đúng như vòng dev trước). Tôi KHÔNG đổi code sản phẩm hay file test của repo; dùng plugin pytest nằm ngoài repo (`scratchpad/qa_pgshim.py`) làm hai việc: mở proxy TCP `127.0.0.1:55750` -> container qua `docker exec -i ... nc 127.0.0.1 5432`, và gán lại `vision_trace_fixtures.TEST_DATABASE_URL` sang cổng 55750. Với shim, các test DB chạy thật (0 skip trong các nhóm trên). Lưu ý cho máy này: đổi cổng fixture (ngoài dải 55434-55533 và 55334-55433...) hoặc đặt `net.ipv4` excluded range lại; đây là lỗi hạ tầng, không phải code phase 15b.

## Kiểm hành vi (ánh xạ chi tiết ở test-cases.md)
- Ba ca cờ (bật / tắt không type / tắt có type): có test BE (use case + route) và spec Playwright; PASS.
- 404 đồng nhất (viewer, tenant khác, session lạ), `Cache-Control: private, no-store`, không lộ giá trị gõ/operation_id/locator_id/ref/bbox, không log, không ghi DB, `/trace` không đổi, chỉ thêm một route GET: PASS.
- `step_index` lặp: giữ cả hai mục; form dùng vị trí mảng làm khoá; PASS.
- Phase 15 riêng tư (giá trị gõ không vào URL/storage/console/request khác): spec `QA phase 15: typed value stays...` PASS.
- Test QA thêm (`tests/test_qa_p15b_draft_inputs.py`, 5 ca, đã `hgraph add agent-task-draft`): độ dài theo ký tự (Unicode/emoji, 500 ký tự) và POST chấp nhận đúng độ dài đó; nhiều step_index khác nhau giữ thứ tự; tên locator Unicode; cờ tắt không lộ tên/độ dài; header.
- Test tái hiện bug cũ: không áp dụng (đây là tính năng thêm, không phải fix); nợ "người nhập chỉ biết sai sau `input_value_mismatch`" được phủ bởi C01-C03.

## Chưa test được
- Gọi route thật trên stack `localhost:7000`: stack chạy image cũ. `openapi.json` không có path `test-draft` nào (cả POST), GET `.../5089e2be-.../test-draft/inputs` (phiên agent_loop `completed`) trả 404 như mọi route không tồn tại. Không rebuild theo yêu cầu.
- Chưa xem ảnh chụp màn hình form bằng mắt; kiểm bằng khẳng định text của spec.
- `hgraph check --changed` vẫn báo `uncovered-changed` cho nhóm file có tiền tố `auto-at-ui/` (false positive đã biết cho file tracked chưa commit, gồm cả file phase 15b như `vision.py`, `generation-api.ts`, `generation-types.ts`, `vision-dashboard.spec.ts`, đã nằm trong graph) và file của các phase khác (agent_loop.py, evidence.py, ...). Không có `drift`/`stale-file`; `hgraph check` đầy đủ sạch. File QA mới của tôi đã được thêm vào graph.
- Stress test: không cần (route đọc một vết sẵn có, không vòng lặp tập lớn / query mới / lock).

## Thay đổi của QA
- Mới `tests/test_qa_p15b_draft_inputs.py` (chỉ test).
- `docs/graphs/agent-task-draft.md`: thêm dòng file test trên qua `hgraph add`.
- Không sửa code sản phẩm; không commit.

QA VERDICT: PASS
