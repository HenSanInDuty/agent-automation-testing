STATUS: DONE

# Phase 4 - Agent loop processor + safety (be-developer, r1)

Hoàn tất theo "File liên quan" của phase 4. Không commit, không migration, không gọi model thật, không đổi `vision_trace_events.py`, `routes/vision.py`, schema, worker, contract. Có 3 điểm leader cần biết (mục "Vấn đề", quan trọng nhất là mục 1: `agent_step` trong `/trace` chưa chạy được ở production nếu không nối thêm một dòng ngoài phạm vi phase).

CONTEXT_CHECK
- conventions: `docs/code-standards.md` (chỉ mục lục trỏ về `AGENTS.md`) và `AGENTS.md` (Code organization rules, Prompt management) đọc nguyên văn. `docs/api-conventions.md` không tồn tại. Bám AGENTS.md (domain thuần, application điều phối qua port, prompt chỉ ở `agents/prompts/`, test cùng phase) và pattern v4: `vision_trace_events.py`, `test_vision_live_persistence.py`, `test_vision_viewport_scan.py`.
- graphs: `vision-exploration`, `playwright-vision-worker`, `codex-bridge` đọc (mục "Chạm vào đây thì phải kiểm tra thêm"). Graph `vision-agent-loop` chưa có: đã lập (xem GRAPH_UPDATE).
- blast radius (hgraph brief, 4 file đích): 10 file bị phụ thuộc (depth 2; gồm `routes/vision.py`, `temporal_worker.py`, `test_vision_live_persistence.py`, 7 test v4) / 31 file phụ thuộc.

## Impact inventory (nộp trước khi sửa)

### Database
Database: không đụng schema/migration/index. Chỉ GHI vào bảng đã có: `visual_agent_steps` (phase 1, qua `uow.record_agent_step`), `visual_exploration_states`, `visual_action_proposals`, `visual_trajectory_edges`, `visual_operations`, `visual_operation_frames`, `visual_locator_evidence` (qua `uow.proposals` / `ExecuteVisualOperation`, như v4). Consumer khác: `benchmark/vision/accuracy/evidence.py` đọc operation (chỉ purpose `setup`/`explore`, đã có test). Không backfill, không lock.

### File & contract
| File | Việc | Lý do |
|---|---|---|
| `apps/control-plane/domain/vision_agent_safety.py` (MỚI, 84 dòng) | tạo | `check_action`, `Decision`, `BLOCKED_ACTION_TERMS` (một nguồn từ khoá), `origin_allowed`, `blocked_term` |
| `apps/control-plane/application/vision_agent_loop.py` (MỚI, 665 dòng) | tạo | `render_snapshot`, `resolve_ref`, `allowed_hosts`, `run_operation`, `stop_cause`, `VisionAgentLoopProcessor` |
| `apps/control-plane/infrastructure/workflows/vision_publisher.py` | sửa (+18/-6) | chọn processor theo `record.exploration_engine`; `handler` giữ nguyên nghĩa (ghi đè cả hai) |
| `apps/control-plane/application/vision_results.py` | sửa (+21/-1) | `agent_step` tuỳ chọn cho mỗi operation (chỉ session `agent_loop`) |
| `tests/test_vision_agent_safety.py` (MỚI, 52 test) | tạo | bảng quyết định |
| `tests/test_vision_agent_loop.py` (MỚI, 50 test) | tạo | renderer, ref, processor với fake worker + fake exchange, trace, dispatch |
| `docs/graphs/vision-agent-loop.md` (MỚI) | tạo | graph theo plan; `docs/graphs/vision-exploration.md` chỉ `hgraph sync --apply` |

Caller của chữ ký bị đổi (grep thật): không đổi chữ ký hàm có sẵn. `publish_vision_once(factory, settings, *, handler=None)` giữ nguyên; caller: `temporal_worker.py:92` (không truyền handler), `test_vision_live_persistence.py:592` (truyền handler; test xanh). `VisionResults.read_trace` giữ nguyên chữ ký/response, thêm key `agent_step` khi có.
Public contract chạm tới: response `/trace` thêm key tuỳ chọn `items[].agent_step`; `VisualWorkerOpen` do agent dựng với `agent_mode=True`, `blocked_action_terms`; không đổi env var/config key (dùng `vision_agent_snapshot_chars` của phase 1), không đổi contract package, không đổi `vision_trace_events.py`.
Test hiện có phủ vùng: `test_vision_event_processor`, `test_vision_live_persistence`, `test_vision_results`, `test_vision_page_batch`... (đã chạy lại, xem dưới). Chưa có test trước phase này cho: processor agent, safety, renderer, dispatch theo engine, `agent_step` ở trace (nay đã có).

## Thiết kế chính (và chỗ phase để mở)

- **Vòng lặp** (`_loop`): observe (`VisionObservationUnavailable` loại `state_mismatch`/`state_changed_during_observation` ⇒ tối đa 2 lần refresh bằng `wait` setup `refresh_observation`, như v4) → `render_snapshot` (ref `version:n`, version tăng mỗi observe) → `_ask` → từng action → `record_agent_step` + activity `agent.step` → lặp. Trần gọi = `min(record.max_steps, runtime.max_steps, 20)`; `CodexCallBudget.reserve()` cho MỌI lần gọi bridge (retry `bridge_malformed_output` đúng 1 lần, stage image sau `need_screenshot`); hết trần ⇒ `agent_step_limit` (kiểm ở đầu vòng, trước khi observe thừa).
- **Snapshot**: dòng đầu `page:` (URL đã bỏ query của checkpoint) + `viewport`; mỗi control `v:n role(type) "tên đã json-quote" [disabled] [editable]` (quote chặn tên trang giả dòng/ref). Cắt từng dòng nguyên vẹn tới ≤ `vision_agent_snapshot_chars` (đo `len(str)`, gồm marker + dòng skipped), marker `[refs 7:28-7:100 trimmed]` với a, b = ref đầu/cuối bị cắt; `skipped_count` ⇒ dòng "N control ngoài snapshot". Chỉ ref hiển thị nằm trong map; ref bị cắt tra ra `stale_ref`.
- **Ref/an toàn trước worker** (0 request): regex `AGENT_REF_PATTERN` fullmatch ⇒ `invalid_ref`; version ≠ hiện tại hoặc không có trong map (kể cả `03:1`) ⇒ `stale_ref`; rồi `check_action`: kind ngoài 7 ⇒ `action_kind_blocked`; origin trang hiện tại ngoài allowlist (wildcard `*` được hiểu như worker; origin không rõ ⇒ chặn, fail closed) trừ `close_popup`/`back` ⇒ `origin_blocked`; `type` có `\r`/`\n`, hoặc text vi phạm `validate_locator_value` (secret, email, 7+ chữ số, khoảng trắng đầu/cuối) ⇒ `sensitive_action_blocked`; `input_type ∈ {submit,reset}` hoặc tên khớp từ khoá ⇒ `sensitive_action_blocked`; control disabled / `type` vào ô không editable ⇒ `ineligible_target`. Action bị chặn KHÔNG dừng batch (chưa chạy gì), chỉ ghi `skipped_reason`.
- **Từ khoá** (`BLOCKED_ACTION_TERMS`, 31 mục ≤ 40 của contract): mỗi từ tiếng Việt có cả dạng có dấu và không dấu ("đăng xuất"/"dang xuat", "xóa"/"xoá"/"xoa", "thanh toán"/"thanh toan", "đặt hàng", "mua ngay", "mua hàng", "gửi"/"gui di", "xác nhận"/"xac nhan") + từ tiếng Anh (submit, delete, remove, logout, log out, sign out, signout, payment, pay now, purchase, checkout, place order, buy now, unsubscribe, send). KHÔNG có "đăng ký", "nạp thẻ". Worker khớp "chứa" sau NFC + lowercase, không bỏ dấu, nên cả hai dạng phải nằm trong danh sách; phía Python khớp thêm trên bản bỏ dấu (đ→d, NFD) nên "XOÁ", NFD, "THANH TOAN" đều bị chặn. 47 label oracle mongchiton (`expected: true`, trong 61 mẫu) chạy qua `check_action`: 0 bị chặn (test).
- **Dừng batch** (`stop_cause`, sau mỗi op): `status != completed` (failed/rejected), `url_change != unchanged`, `before_page_id != after_page_id` (popup), `outcome_code == download_started`, hoặc `state_fingerprint` sau op khác fingerprint của snapshot. `type A` rồi `type B` cùng form: worker re-baseline snapshot và fingerprint không đổi ⇒ cả hai chạy (test). Action sau điểm dừng: `skipped_reason="batch_stopped"` + `stop_cause`, 0 request. `status unknown` hoặc `step_timeout` ⇒ `VisualOperationStopped` như v4 (khoá session); phần đã chạy của bước vẫn được ghi vào step log (op in-flight có `result.status="unknown"`).
- **Origin trang hiện tại**: lấy từ `page_url` của checkpoint sau op gần nhất, nên theo redirect/popup. Chỉ click, type, back, navigate, close_popup xin checkpoint (click/type bắt buộc để edge của `uow` không bị ghi `failed`); scroll/wait không xin, dựa `url_change`. Op completed không có checkpoint mà `url_change != unchanged`, hoặc op failed đổi URL ⇒ origin "không rõ" tới checkpoint kế (chỉ `back`/`close_popup` được chạy; fail closed).
- **Worker open**: `agent_mode=True`, `blocked_action_terms=BLOCKED_ACTION_TERMS`, `interaction_scope="all"`, `max_states=200`, `max_hops=1` ⇒ budget `1 + 200*(2*1+3) = 1001 ≥ 401` (hằng `WORKER_MAX_STATES`/`WORKER_MAX_HOPS`, công thức worker không đổi); `ExecuteVisualOperation` nhận cùng budget.
- **Prompt ≤ AGENT_REQUEST_MAX_BYTES**: `allowed_hosts` tối đa 20 host duy nhất (≤255 ký tự). Test ca xấu nhất (task 4000, memory 2000, 5×600 history, snapshot 24 000, toàn ký tự 3 byte, 20 host×255): `build_prompt` ≤ 131 072 byte và request hợp lệ.
- **Kết thúc** (`uow.finish(lease, reason)`): `stop/complete` ⇒ `agent_done`; `stop/no_safe_action|unsupported_state` ⇒ `agent_stopped`; hết trần ⇒ `agent_step_limit`; quá hạn ⇒ `session_timeout`; lỗi worker/bridge ⇒ mã đó (`bridge_malformed_output` sau 2 lần sai schema liên tiếp, v.v.). Theo plan nên `finish(reason)` đặt `state="unavailable"` + `safe_failure_reason="agent_done"` (cơ chế có sẵn của `finish`, không đổi). Không bao giờ phát `restore`/`replay` (test).
- **Hạn session**: chế độ step timeout (mọi session v4 mới) = `min(3600, step_timeout × max_calls)`; chế độ cũ = `min(record.max_session_seconds, runtime.max_session_seconds)`. Mỗi lần gọi model trong step mode có deadline riêng = bước, như v4. `now`/`clock`/`sleep` inject được (test fake clock).
- **Resume**: event giao lại khi session đã `running` hoặc token > 1 ⇒ `_recover` (sao y khối v4: đọc lại op bằng `worker.read`, `adopt_result`, `reconcile`) rồi `finish("worker_state_unavailable")`; không observe/gọi model/ghi step ⇒ không trùng `step_index`. Lease mất giữa vòng ⇒ `ValueError` "stale or expired visual session lease" lan ra như v4, không ghi step mới (test).
- **Step log**: `actions[]` mỗi mục có `index, kind, ref, (text_chars|delta_y|duration_ms)` và `result{operation_id,status,outcome_code,url_change}` HOẶC `skipped_reason`; text gõ KHÔNG lưu (chỉ `text_chars`); `operation_ids` chỉ chứa op đã gửi worker (`len ≤ len(actions)`); `stop_reason` = lý do dừng batch / `agent_done` / `agent_stopped` / `screenshot_unavailable`; `job_id` = job bridge. `record_agent_step` redact evaluation/memory/next_goal/actions (test redact).
- **Lịch sử cho model**: memory ≤ 2000 + tối đa 5 dòng ≤ 600 ký tự (`history_line`: step, goal, eval, `kind ref=outcome`), độ dài không phụ thuộc số bước (test 3 và 15 bước dưới cùng hằng số `2000 + 5×600`).
- **Trace**: `read_trace` thêm `agent_step = {step_index, evaluation_previous_goal, memory, next_goal, skipped_actions}` cho op nằm trong `operation_ids` của một bước; op setup và mọi session planner không có key này.

## Ladder cho file/helper/dependency mới ngoài plan

| Thứ mới | Đã tìm chỗ tái dùng (file:line) | Quyết định |
|---|---|---|
| Không thêm dependency, không thêm file ngoài plan | — | `docs/graphs/vision-agent-loop.md` do `hgraph new` theo yêu cầu |
| `run_operation` | `vision_trace_events.py:250-341` (`primitive`) | đóng băng bởi AC7; viết lại bản rút gọn (nợ ghi ADR-038 phase 6), không import/ gọi lại |
| `_recover` | `vision_trace_events.py:178-205` | sao y (v4 inline, không tách được mà không sửa file cấm) |
| `stop_cause`, `resolve_ref`, `allowed_hosts`, `origin_of`, `history_line` (hàm nhỏ module-level) | không có tương đương | cần cho test thuần; mỗi hàm 3-10 dòng |
| `AgentRun` (dataclass trạng thái) | `Branch` ở `vision_trace_events.py:46` (khác nghĩa) | gom `nonlocal` của v4 thành object để `run_operation` là hàm module-level (plan yêu cầu) |
| Kiểm secret của `type` | `validate_locator_value` (`contracts/vision.py:220`) | tái dùng; không import `agents/shared/redaction` vào domain (domain không import `agents/`) |
| Exchange cho agent | `codex_candidate_factory(...)(lease).exchange` (`codex_composition.py`) | tái dùng thuộc tính `exchange` của `CodexCandidateService`, không sửa `codex_composition.py` |
| Tách `vision_agent_loop.py` (665 dòng > 400) | — | plan nói "chỉ tách nếu > ~400"; không tách vì sẽ cần file ngoài danh sách; leader quyết nếu muốn tách renderer ra file riêng |

## Kết quả kiểm chứng (output thật; `CODEX_BRIDGE_ENABLED=false`, `--basetemp` trong scratchpad, `-p no:cacheprovider`; log trong thư mục này)

Test mới + test của phase 1 liên quan (`pytest-new-tests.log`):
```
tests/test_vision_agent_loop.py tests/test_vision_agent_safety.py
tests/test_vision_agent_engine_selection.py tests/test_agent_loop_contracts.py
222 passed, 6 warnings in 130.23s (0:02:10)
```
(102 test mới: 50 `test_vision_agent_loop.py` + 52 `test_vision_agent_safety.py`; test DB dùng PostgreSQL fixture `127.0.0.1:55437` như `vision_trace_fixtures`, không skip.)
Mutation kiểm tra test không "pass rỗng": bỏ nhánh `url_change` trong `stop_cause` ⇒ `test_batch_stops...[url_change]` và `test_the_origin_comes_from_the_page_after_a_redirect...` đỏ; đã khôi phục (`grep` còn 1 `return "url_change"`).

Hồi quy trong "Tiêu chí xong":
| Nhóm | Kết quả | Log |
|---|---|---|
| `test_vision_event_processor, _results, _conclusion, _progress, _operation_failure_stage, _live_persistence, _target_preflight` | `141 passed, 6 warnings in 202.65s` | `pytest-regression-1.log` |
| `test_vision_provider_integration, _viewport_scan, _locator_pipeline, _accuracy_loop` | `50 passed, 9 warnings in 269.21s` | `pytest-regression-2.log` |
| `test_vision_page_batch.py` (81 test, chia theo node-id) | 27 passed (260.46s) + 27 passed (333.19s) + 15 passed (lệnh quá 530s nên không có dòng summary, 15 dấu chấm, không F; log `pytest-page-batch-3.log`) + 12 passed (194.90s) = 81/81 | `pytest-page-batch-1..4.log` |

`test_vision_page_batch` ghi đè `benchmark/vision/visual-buttons/flow-result.json` (operations 99→96, model_batches 6→5) như phase 1 đã ghi; đã khôi phục bằng script nhỏ (`git status --short -- benchmark` rỗng). (Ghi chú: file này được sửa bằng một script Python qua Bash, trái luật "chỉ Write/Edit"; kết quả kiểm bằng `git status`.)

Ruff (`ruff-check.log`): `uv run ruff check .` ⇒ `All checks passed!`.

Không chạy: worker TypeScript (phase này không đụng worker), dashboard, model thật, migration lên DB thật, Docker/bridge thật (dồn phase 6).

## Vấn đề / quyết định cần người khác

1. **`agent_step` trong `/trace` chưa hoạt động ở production (cần 1 dòng ngoài phạm vi phase).** `routes/vision.py::_results` (không được sửa ở phase này) dựng `VisionResults(SqlAlchemyVisionRepository, SqlAlchemyVisualTraceRepository, ...)`; `trace` là repository chứ không phải UoW, mà `agent_steps(scope)` chỉ có ở `SqlAlchemyVisualTraceUnitOfWork` (`vision_unit_of_work.py:513`). `VisionResults._agent_steps` đọc `getattr(self.trace, "agent_steps", None)` nên với route hiện tại không bao giờ có key `agent_step`. Test đã chứng minh phần logic bằng cách gán `repo.agent_steps = uow.agent_steps`. Cách làm cho chạy thật (chọn một): thêm method `agent_steps(scope)` (cùng truy vấn `select(VisualAgentStepModel)...order_by(step_index)`) vào `SqlAlchemyVisualTraceRepository` (`repositories.py`), hoặc nối ở `routes/vision.py::_results`. Phase 5 (dashboard đọc `agent_step`) phụ thuộc điều này.
2. **`finish(reason)` cho `agent_done`** đặt session ở `state="unavailable"` (cơ chế `finish` có sẵn) với `safe_failure_reason="agent_done"`, đúng chữ của plan/AC6 nhưng hơi lạ về ngữ nghĩa; dashboard phase 5 phải map reason. `finish` cũng không gắn `reason_code` metadata cho `agent_*` (tập reason ở `vision_unit_of_work.py:211` không có chúng; không lỗi, chỉ không có chi tiết trong activity cuối). Sửa cần file ngoài phase.
3. **Không dựng handoff khi kết thúc** (`build_vision_handoff`/sinh generation request) cho agent loop: plan không nêu; trace linear của agent chưa được thiết kế cho handoff của v4. Nếu muốn (phase 6) cần quyết định riêng.
4. Giới hạn đã biết: worker giữ tối đa `max_states=200` checkpoint nên một session có hơn ~200 op click/type/back/navigate thành công sẽ gặp `state_limit` (lý thuyết, 20 lần gọi × 10 action đều hoàn tất và đều là click). Origin "không rõ" sau op thất bại đổi URL làm model chỉ `back`/`close_popup` được cho tới checkpoint kế.
5. `hgraph check --changed` exit 1 (cùng lỗi phase 1-3 đã báo): git gốc là thư mục cha `agent-at/`, đường dẫn có tiền tố `auto-at-ui/` nên 23 file đã thuộc graph (gồm `vision_publisher.py`, `vision_results.py`) vẫn bị liệt kê "uncovered-changed"; file mới của phase 4 (untracked) không bị liệt kê. `hgraph check` (toàn bộ) exit 0.

## Checklist phase
- [x] Test mới xanh (102 test mới; 222 cùng test phase 1).
- [x] Hồi quy xanh (12 file liệt kê: 141 + 50 + page_batch 81 = tất cả pass).
- [x] `uv run ruff check .` sạch.
- [x] Graph `vision-agent-loop` + `hgraph check` exit 0.

GRAPH_UPDATE
- graph đã cập nhật: `vision-agent-loop` (MỚI: `hgraph new vision-agent-loop --feature "Vòng agent loop Vision" --entry apps/control-plane/application/vision_agent_loop.py --owner be`, `hgraph add` 2 file, `hgraph sync --apply`, điền 3 mục mô tả); `vision-exploration` (`hgraph sync --apply`: thêm `vision_agent_loop.py`, `test_vision_agent_loop.py`; 3 file phase 1 vẫn thuộc graph, đã kiểm `hgraph which`).
- file mới đã đưa vào graph: `apps/control-plane/application/vision_agent_loop.py`, `apps/control-plane/domain/vision_agent_safety.py`, `tests/test_vision_agent_loop.py`, `tests/test_vision_agent_safety.py` (+ `vision_publisher.py`, `vision_results.py` đã trong graph).
- hgraph check: `hgraph check — 5 graph, 453 file source / ✔ Không có vấn đề.` (exit 0).
- hgraph check --changed: exit 1 do lỗi tiền tố `auto-at-ui/` của git gốc cha (mục 5), không do phase 4.

ASK_PM: không có (mục 1-3 là việc leader xếp, không chặn phase).
