STATUS: FAIL

Lý do FAIL: không AC nào hoàn toàn không-test-được, nhưng AC3 (phần "link download" ở control-plane) và AC5 (test "300 element") không thể kiểm chứng đúng như viết vì mâu thuẫn với contract hiện có; AC6 chỉ đo được "bằng chứng đầy đủ" chứ không đo chất lượng (cần viết lại). Plan cần sửa các mục "Phải sửa" dưới đây trước khi code.

## 1. Acceptance criteria

| AC | Kiểm chứng ở | Đánh giá | Viết lại đề xuất |
|---|---|---|---|
| AC1 | P4 `test_vision_agent_loop` (fake worker + fake exchange), P1 `record_agent_step` | Đo được. Thiếu: "operation_ids" khi action bị bỏ qua/chặn (không có operation) | Thêm: "action bị chặn/bỏ qua có mặt trong `actions` với `skipped_reason`, không có trong `operation_ids`; `len(operation_ids) <= len(actions)`" |
| AC2 | P4 fake worker đếm call prepare/execute = 0; P2 `stale_dom_snapshot` ở worker | Đo được. Thiếu biên: ref sai format, version đúng nhưng index không tồn tại, version tương lai, ref từ bước trước nhưng cùng batch sau batch-stop | "Ref có version ≠ snapshot hiện tại, hoặc không có trong map, hoặc sai regex → mã `stale_ref` (hoặc `invalid_ref` cho sai format); số call worker prepare/execute của action đó = 0" |
| AC3 | P4 `test_vision_agent_safety` + loop; P2 worker spec | Đo được ở worker. Ở control-plane KHÔNG: `CodexDomElement` (codex_bridge.py:103) chỉ có role/name/input_type/enabled/editable, không có href/download/form-membership, nên "link download" và "submit mặc định trong form" chỉ worker bắt được. Từ khoá: AC không nêu danh sách; hai danh sách (Py/TS) có thể lệch | "Control-plane chặn: kind ngoài 7, page ngoài allowlist (trừ close_popup/back), `input_type` submit/reset, name khớp danh sách từ khoá dùng chung. Worker chặn thêm: `a[download]`, submit mặc định trong form. Mỗi trường hợp: 0 call tới worker (CP) hoặc 0 request mạng/0 thay đổi DOM (worker), step log có reason code." Thêm test parity: danh sách từ khoá Py = TS (đọc cùng nguồn hoặc so sánh). |
| AC4 | P4 loop test (chỉ ví dụ `url_change`) | Mơ hồ ở "đổi state_fingerprint (ngoài re-baseline form)". Test mới chỉ phủ url_change | "Với mỗi điều kiện trong {url_change, fingerprint đổi không do form, popup mới, download, op status ≠ completed}: các action sau trong batch có 0 call worker; bước kế gọi observe_dom đúng 1 lần. Với `type A` rồi `type B` (chỉ privateForms đổi): cả hai chạy." Cần 5 test tham số hoá. |
| AC5 | P4 SnapshotRenderer/loop test, P1 context limits | Đo được nhưng test "snapshot 300 element" mâu thuẫn contract: `CodexDomObservation.elements max_length=100`, 64 KB. Ngoài ra "ký tự" vs byte (tiếng Việt) chưa chốt; "không tăng tuyến tính" mơ hồ | "Renderer nhận ≤100 element + `total_candidates` (có thể 300) → phần snapshot ≤ 24 000 ký tự (len(str)), marker `[refs a-b trimmed]` với a,b khớp ref bị cắt thực tế. Độ dài phần history+memory ở bước 6 và bước 20 đều ≤ hằng số cấu hình (memory ≤2000 ký tự, history ≤5 bước × giới hạn)". Test 300 element phải ở tầng renderer (không qua `CodexDomObservation`), hoặc plan nêu rõ sửa trần 100. |
| AC6 | P4 offline (evidence.export_operation chấp nhận mọi op, không restore/replay); P6 live | Live phụ thuộc model, không tất định. "score.json tồn tại" không chứng minh chất lượng. Chấp nhận được nếu đặt đúng là AC về tính đầy đủ bằng chứng | "Session terminal với reason ∈ {agent_done, agent_stopped, agent_step_limit, session_timeout}, ≠ unsafe_replay; `run.py collect` + `evaluate` thoát 0 và sinh `score.json` schema hợp lệ; `git diff` rỗng trên `metrics.py` + oracle; 0 operation `restore`/`replay`; số `sensitive_action_blocked` trên mct-xx của oracle = 0. Không có ngưỡng C/A (ghi rõ là đo, không gate)." |
| AC7 | P1 sha256 test; P3 byte-identical; hồi quy P0-P6 | Đo được nhưng HẠ TẦNG THIẾU: sha256 `CodexOutput` và snapshot prompt/schema v4 "trước phase" chưa có bước nào ghi lại. P0 không ghi | P0 thêm bước: sinh và commit vào `tests/fixtures/` (hoặc `reports/phase-00/`) sha256 `TypeAdapter(CodexOutput).json_schema()`, bytes prompt+schema `codex-dom-v11` cho 1 request mẫu, sha256 `vision-contract.generated.ts` phần v4. Mọi test byte-identical so với file này, không hằng số tự khai trong test. |

## 2. Từng phase

**P0 (qa skip: hợp lý).** Đo được (số pass/fail/skip, alembic head). Thiếu: lưu hash/snapshot v4 (xem AC7); ghi môi trường (DB có chạy không, vì 69 test DB-gated bị skip: nếu skip mốc thì P1 migration up/down không có đối chứng).

**P1 (required: đúng, đụng DB + contract).**
- Đo được: alembic up/down, sha256, contract tests.
- Thiếu biên: DB CHECK/validator cho `exploration_engine` ngoài {planner, agent_loop}; session cũ trả `engine="planner"`; actions đúng 1 và đúng 10 (biên), 11 bị từ chối; `delta_y` âm/0/rất lớn, `duration_ms` âm; `text` unicode tiếng Việt + độ dài tối đa; `navigate` chỉ nhận ref=null (không có URL tuỳ ý, K2); memory đúng 2000 và 2001 ký tự; tenant isolation của `visual_agent_steps`; fence mất lease thì `record_agent_step` bị từ chối; downgrade khi đã có dữ liệu.
- Bước migration cần PG thật: đánh dấu rõ test này DB-gated, chạy trong QA bằng `DATABASE_URL`; nếu skip thì tiêu chí "alembic up/down sạch" chưa chứng minh.
- Không có cách dashboard biết cờ bật (xem P5).

**P2 (required: đúng, bảo mật + hành vi trình duyệt).**
- Đo được: spec Playwright.
- Thiếu: (a) `action_outcome_unknown` vẫn khoá session ở agent mode (K4 nói rõ nhưng test chỉ kiểm `confirm()`); (b) biến thể dialog: `alert`, `prompt`, `beforeunload`; (c) download bị cancel xong, op kế vẫn chạy được và không đặt `policyFailure`; download không do action (ngoài op) giữ như v4; (d) từ khoá nhạy cảm: hoa/thường, có/không dấu ("xoá"/"xoa"/NFD), và ĐĂNG KÝ/NẠP THẺ không bị chặn (hiện chỉ P4 có, phải có cả ở worker vì danh sách riêng); (e) submit bằng `type` + Enter hoặc phím trong form (bypass nút); (f) điều hướng top-level cùng tab ra origin ngoài (không phải popup) rồi `back`; redirect từ origin trong allowlist ra ngoài; so sánh origin khác cổng/scheme/subdomain; (g) sub-resource ngoài origin (ảnh/XHR) KHÔNG bị chặn (K3); (h) "Không có nhánh chạy khi agent_mode=false" chỉ là "rà diff" (không đo được) → thay bằng: chạy lại toàn bộ spec v4 hiện có với `agent_mode` mặc định, thêm 2 test đối chứng v4 (snapshot limit, hop_limit vẫn kích hoạt).
- Môi trường: Chromium thật (`npx playwright install`), `--workers=1`. Rủi ro flaky: popup/download/dialog timing, settle; dùng fixture tĩnh cục bộ (không mạng ngoài), chạy lại 3 lần mỗi spec mới để loại flaky. Fixture `agent-loop-target.ts` chưa có (chỉ có thư mục `fixtures/`).
- "25 click không chạm hop_limit": cần xác nhận giá trị limit v4 < 25, nếu không test vô nghĩa. Ghi giá trị limit vào test.

**P3 (qa skip: nên đổi thành required).** Đổi giao thức spool host/container (`agent_context`, dispatch theo `prompt_version`), parser Claude/Codex, sửa `codex_bridge.py` đang sửa dở. P4 dùng fake exchange nên không ai kiểm bridge thật. Nếu giữ skip thì P6 phải có bước QA riêng cho bridge. Thiếu test: thứ tự 5 khối + tiền tố chung (đã có); prompt injection: snapshot/ tên element chứa "ignore instructions" nằm trong khối snapshot, được đánh dấu không tin cậy (kiểm chuỗi, không cam kết miễn nhiễm); độ dài tối đa prompt so `max_output_bytes`; job v4 đi cùng spool với job agent (hai họ xen kẽ); snapshot byte-identical v4 (phụ thuộc P0).

**P4 (required: đúng).**
- Đo được phần lớn. Thiếu case biên quan trọng:
  - Ngân sách: "hết 20 lần gọi" – chưa rõ retry-sai-schema và `need_screenshot` có tính vào 20 không (DB `ck_codex_job_sequence BETWEEN 1 AND 20`, models.py:191 sẽ chặn cứng). Cần quyết và test biên: lần 20 chạy, lần 21 không; retry tiêu tốn budget.
  - `max_requests_per_minute` và `max_cost_usd` có trong Constraints nhưng không có test.
  - `need_screenshot` khi không có consent; `stop` ngay bước 1; model trả toàn action bị chặn (vòng lặp vô hạn trong budget: kiểm kết thúc `agent_step_limit` chứ không treo); action lặp y hệt thất bại liên tiếp.
  - Lease mất giữa vòng (ghi ở rủi ro nhưng không có test trong danh sách) và re-delivery/resume session giữa chừng (unique `session_id, step_index`).
  - Page origin lấy từ đâu (checkpoint `page_url`?) và test redirect; chặn trên popup observe-only.
  - Step log cho action bị bỏ qua sau batch-stop.
  - Nội dung step log đã redact (task/memory chứa secret).
  - `vision_results.py` trace: session planner không có `agent_step` (đối chứng); contract trace thay đổi là public API.
- "snapshot 300 element": xem AC5, không hợp lệ qua `CodexDomObservation`.
- Môi trường: fake worker + fake exchange, DB thật cho `record_agent_step`/FK (mẫu `vision_trace_fixtures.py` có sẵn; xác nhận có chạy được không-DB hay DB-gated).

**P5 (required: đúng, luồng UI).**
- Unit test chỉ ở hàm thuần (node:test) — không chứng minh form/ledger render. Tiêu chí "ảnh chụp màn hình" là thủ công, không đo được. Thêm: một e2e (skill ak:agent-browser hoặc spec dashboard sẵn `vision-dashboard.spec.ts` ở worker) với API mock có/không `agent_step`: select engine hiển thị đúng, ledger hiện 3 trường, session planner không có khối agent; viewport 400px không tràn ngang (assert `scrollWidth <= innerWidth`).
- LỖ HỔNG: "chỉ hiện khi API báo cờ bật" nhưng không phase nào thêm field (`VisionPolicyResponse` ở routes/vision.py:77 không có `agent_loop_enabled`). Thêm vào P1 (file liệt kê) hoặc bỏ điều kiện.
- Thiếu: hiển thị mã lỗi chưa biết (fallback), `agent_step` field rỗng/rất dài, tiếng Việt có dấu, giá trị `engine` lạ.

**P6 (required: đúng, phase cuối).**
- Hồi quy đo được (so với baseline P0). Live chạy: cần phép user, token bridge, stack docker; không tất định, chi phí; một vòng/phiên. Tiêu chí xong: xem viết lại AC6.
- "Từ khoá chặn nhầm target oracle" chỉ phát hiện sau chạy live (đắt). Thêm test offline ở P4: chạy `check_action` trên toàn bộ tên element của fixture oracle mongchiton (nếu có inventory trong `benchmark/vision/accuracy/`), kỳ vọng 0 bị chặn.
- `run.py` "chỉ nếu start cần engine": quyết định sớm; nếu sửa, test `test_vision_accuracy_loop.py` đã được nêu.
- Chốt cách kiểm "git diff rỗng trên metrics.py/oracle" bằng lệnh cụ thể: `git diff --exit-code -- benchmark/vision/accuracy/metrics.py <oracle>`.

## 3. Trường `qa:` tổng kết
- P0 skip: đúng. P1, P2, P4, P5, P6 required: đúng. P3 skip: nên required (contract spool nội bộ + không có kiểm bridge thật ở phase khác).

## 4. Môi trường test

| Test | Cần |
|---|---|
| P1 contract, selection (route/app), sha256 | Python thuần; route có thể dùng test client |
| P1 migration up/down, record_agent_step fence/unique | PostgreSQL thật (DB-gated; 69 test skip ở baseline, phải biết `DATABASE_URL` có sẵn để QA chạy) |
| P2 spec | Chromium thật, `--workers=1`; fixture mới chưa có; flaky: popup/dialog/download |
| P3 | fake CLI process (đã có mẫu test_claude_bridge, test_codex_bridge_process) |
| P4 | fake worker + exchange; DB cho UoW (xác nhận) |
| P5 | node:test (không DOM) + e2e browser nếu thêm |
| P6 | docker stack, model live (Claude/Codex bridge), tiền, token hết hạn: không tự động hoá được, chỉ chạy khi user cho phép |

## 5. Danh sách "Phải sửa" trước khi duyệt (đề xuất)
1. P0: ghi hash/snapshot v4 làm đối chứng (AC7, P3).
2. P4/AC5: sửa test "300 element" cho khớp contract (max 100 element, hoặc tách test ở renderer).
3. AC3: nói rõ phần nào chặn ở CP vs worker (element không có href/download); thêm parity danh sách từ khoá; thêm bypass submit bằng Enter.
4. Chốt ngân sách 20 gồm retry/screenshot; thêm test biên 20/21 + rate/phút + cost.
5. P5: thêm cách dashboard biết cờ bật; thêm một e2e UI.
6. P3: đổi qa thành required (hoặc đưa kiểm bridge thật vào P6).
7. Viết lại AC4, AC6 như bảng trên; thêm test K4 `action_outcome_unknown` ở agent mode.
