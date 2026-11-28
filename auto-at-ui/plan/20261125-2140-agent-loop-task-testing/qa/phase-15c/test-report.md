QA VERDICT: PASS

# Phase 15c - báo cáo QA r1

Môi trường: Windows host (uv/pytest, node + tsx của worker, Playwright 1.50.1); container tạm `qa15c-pg` (postgres:17-alpine, cổng 55437) + `qa15c-pytest` (image `auto-at-ui-control-plane`, repo chép vào /tmp/repo), `CODEX_BRIDGE_ENABLED=false`. Cả hai đã `docker rm -f`; không đụng stack `auto-at-ui-*`, không chạy model thật.

Kết quả: file mới `tests/test_qa_p15c_fixes.py` gồm 29 hàm / 41 ca (kể cả parametrize); host `33 passed, 8 skipped`, container (DB) `18 passed, 23 skipped`; mỗi ca chạy ở ít nhất một nơi. 0 fail. Chi tiết: `test-cases.md`.

Bằng chứng tái hiện:
- F1: `QA_CONTRACT_TS=<contract.ts của HEAD>` -> `3 failed, 21 passed` (F1-01/02/08); code mới 24 passed.
- F2: bỏ dòng `seen = ObservedText()` trong vòng quan sát (bản copy trong container) -> `4 failed, 5 passed` (F2-02/03/04/07); code thật 9 passed.

Nhận xét ngoài tiêu chí (không FAIL):
- `ARTIFACT_PLACES_EXPECTED` dùng khớp chuỗi con (`".dat"`, `".html"`): một thành viên tên như `x.data` cũng bị coi là expected. Rủi ro thấp (trace zip chỉ có `.dat` của Playwright); ghi lại để lần quét r2 của phase 16 xem danh sách thành viên.
- Regex traceparent của worker có cờ `i` nên chấp nhận hex hoa; W3C chỉ cho chữ thường. Control plane luôn sinh chữ thường, nên không ảnh hưởng.
- Test route dùng DB giả (monkeypatch `routes.runs`); đường DB thật của route được `tests/test_run_routes.py` phủ (host, DB skip; developer chạy ở container r1 - 2 fail do thiếu DB cổng 5432, môi trường).
- Stress test: không cần - thay đổi không đụng vòng lặp tập lớn, query, job hàng loạt, transaction/lock.

Chưa test được:
- Run thật `POST /runs` -> workflow -> worker image và phiên agent thật trên stack: việc của phase 16 r2 (cần build lại worker image).
- Ca F2 thực tế với model thật (todo-add pass) - cùng lý do.
- Spec TS riêng (`qa-p15c-contract.spec.ts`) không viết: probe pytest chạy đúng `contract.ts` thật qua tsx, cộng spec của developer (`contract.spec.ts` 20 passed).

Graph: `hgraph check` -> `8 graph, 560 file source / Không có vấn đề.`; `hgraph check --changed` -> `uncovered-changed` toàn đường dẫn tiền tố `auto-at-ui/` (false positive đã biết do git root ở thư mục cha; gồm cả file test QA mới, như mọi file test khác). Không có `drift`/`stale-file`.
