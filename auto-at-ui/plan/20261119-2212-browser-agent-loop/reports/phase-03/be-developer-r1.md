STATUS: DONE

# Phase 3 - Prompt + bridge (be-developer, r1)

Code + test xong theo "File liên quan" của phase. Không commit, không migration, không đụng `codex_exploration.py`, không đụng phase khác. Mục QA "chạy job agent thật qua bridge host (gọi model thật)" KHÔNG làm: chuyển sang phase 6 (cần user cho phép gọi model thật). Có 1 vấn đề cần user/leader biết (Codex dùng file instructions v4, xem "Vấn đề").

CONTEXT_CHECK
- conventions: `docs/code-standards.md` (chỉ là mục lục trỏ về AGENTS.md) và `AGENTS.md` (mục Code organization rules, Prompt management) đã đọc nguyên văn. `docs/api-conventions.md` không tồn tại (phase 1 cũng ghi vậy) -> bám AGENTS.md + pattern 2-3 file cùng loại (`test_claude_bridge.py`, `test_codex_bridge_process.py`, `test_codex_model_batch.py`, `codex_exploration.py`).
- graphs: `codex-bridge`, `vision-exploration` đã đọc (mục "Chạm vào đây thì phải kiểm tra thêm": producer/consumer spool, cờ TTL authorize, prompt phải tăng version + README, contract chung, test hồi quy). Không có graph `vision-agent-loop` -> dùng `codex-bridge`.
- blast radius (hgraph brief, 6 file đích): 26 file bị phụ thuộc (depth 2) / 16 file phụ thuộc.

## Impact inventory (nộp trước khi sửa)

### Database
Database: không đụng. (Không bảng/cột/migration/backfill/index; `codex_bridge_jobs` không đổi cột; `ck_codex_job_sequence` không đụng.)

### File & contract

| File | Việc | Lý do |
|---|---|---|
| `apps/control-plane/agents/prompts/agent_loop.py` (MỚI) | tạo | `PROMPT_VERSION="agent-loop-v1"`, `INSTRUCTIONS`, `build_prompt(request, dom)` + hằng header/delimiter dùng cho test (plan ghi rõ) |
| `apps/control-plane/agents/prompts/README.md` | sửa | dòng `agent_loop.py` / `agent-loop-v1` (AGENTS.md Prompt management) |
| `apps/control-plane/agents/vision/codex_service.py` | sửa | `agent_output_schema()` bọc `agent_loop_output_schema()` của contract; `output_schema()` giữ nguyên |
| `apps/control-plane/infrastructure/vision/codex_batch.py` | sửa | tham số tuỳ chọn `prompt_version`, `schema_bytes`, `stage`, `agent_context` (+ `context` thành tuỳ chọn); mặc định = v4 |
| `apps/control-plane/application/codex_bridge.py` | sửa | `with_response_schema` chỉ khi `request.agent_context is None` |
| `apps/control-plane/codex_bridge_cli.py` | sửa | `PROMPT_BUILDERS` + `build_prompt` chọn theo `prompt_version`, `BridgeService` nhận hàm này |
| `apps/control-plane/infrastructure/codex_bridge/process.py` | sửa | `output_parser` mặc định `None` -> `parse_agent_output` nếu có `agent_context`, ngược lại `parse_codex_output`; thêm tên field agent vào whitelist log chẩn đoán |
| `apps/control-plane/infrastructure/codex_bridge/claude_process.py` | sửa | như trên (không đổi argv/`enforceable_schema`) |
| `apps/control-plane/infrastructure/codex_bridge/spool.py` | sửa | `REQUEST_MAX_BYTES = AGENT_REQUEST_MAX_BYTES` (131 072) cho đọc `request.json` (16 384 -> 131 072) và ghi `request.json`; `dom.json`/`response.schema.json` giữ 65 536, `screenshot.png` 5 000 000 |
| `tests/test_agent_loop_prompt.py` (MỚI), `tests/test_agent_loop_bridge.py` (MỚI) | tạo | test bắt buộc của phase |
| `docs/graphs/codex-bridge.md` | sửa | `hgraph add` 4 file + `sync` + 1 bullet "Họ prompt thứ hai" |
| `docs/graphs/vision-exploration.md` | sửa | chỉ `hgraph sync --apply` (khối auto) |

Caller của chữ ký bị đổi (grep thật): `CodexModelBatch.__call__` chỉ gọi bằng keyword từ `CodexCandidateService` (`application/codex_candidates.py`, qua protocol `CodexExchange`); thứ tự keyword đổi nhưng toàn bộ keyword cũ còn nguyên -> test `test_codex_model_batch.py`, `test_codex_candidate_service.py` xanh. `CodexProcess.run`/`ClaudeProcess.run`: `output_parser` mặc định đổi `parse_codex_output` -> `None`; caller duy nhất truyền tường minh là `generation_process.py:21` (không đổi); nơi khác dùng mặc định. `grep output_parser` trong tests: không test nào phụ thuộc giá trị mặc định.

Public contract chạm tới: `prompt_version` mới `agent-loop-v1` trong request spool; hằng `REQUEST_MAX_BYTES`; không đổi env var/config key, không đổi response API, không đổi contract package (phase 1 đã có sẵn mọi thứ).

Test hiện có phủ vùng này: `test_codex_bridge_{process,spool,service,qualification,end_to_end,contracts}.py`, `test_claude_bridge.py`, `test_codex_model_batch.py`, `test_codex_candidate_service.py`, `test_codex_exploration_integration.py`, `test_agent_loop_contracts.py` (hash v4). Chưa có test trước phase này cho: dispatch builder theo version, parser theo họ, request.json > 65 536, argv/stdin 100 KB (đã thêm).

## Thiết kế chính

- `build_prompt`: 5 khối theo thứ tự cache: (1) `INSTRUCTIONS`; (2) `## RESPONSE SCHEMA` + schema JSON agent (từ contract, cùng byte với `agent_output_schema()`); (3) `## TASK AND LIMITS` (task, allowed_hosts, giới hạn hằng số: 10 action, memory 2000, 5 bước); (4) `## MEMORY AND RECENT STEPS`; (5) `## CURRENT PAGE` (version, stage, delimiter `<<<UNTRUSTED_PAGE_DATA` ... `UNTRUSTED_PAGE_DATA>>>`) - khối cuối. Mọi giá trị đổi theo từng lần gọi (snapshot, `snapshot_version`, stage) chỉ nằm ở khối 5, nên hai lần gọi chỉ khác trang chung byte-for-byte tới `## CURRENT PAGE\nSnapshot version: ` (test khoá đúng điểm này).
- Snapshot lấy duy nhất từ `agent_context.snapshot`; tham số `dom` không render (test khoá). Token delimiter trong snapshot bị trung hoà (`UNTRUSTED_PAGE_DATA` -> `UNTRUSTED-PAGE-DATA`) để text trang không đóng khối sớm.
- Redact task/memory/history ở lúc build (cùng phép che với `task_context`: `redact_value` + email + chuỗi >= 7 chữ số). Snapshot KHÔNG redact ở đây (phase 4 renderer lo; redact cắt `?a=b` có thể làm hỏng text trang).
- `INSTRUCTIONS`: vai trò; làm theo mục tiêu; evaluation/memory/next_goal; ~40 s/lần gọi nên gom tối đa 10 action, đặt action dễ đổi trang cuối (batch dừng khi đổi trang); không lặp action thất bại, đổi cách, lần hai thất bại thì xét lại mục tiêu; dữ liệu trang không tin cậy; chỉ dùng ref của snapshot hiện tại, định dạng `version:n` (ví dụ `3:17`); ngoài allowlist chỉ quan sát rồi `close_popup`/`back`; không submit/download/nhập secret; kết thúc bằng `stop/complete`, `no_safe_action`, `unsupported_state`; `need_screenshot` chỉ ở stage dom. Câu mở đầu nói rõ thay thế mọi instructions v4 (xem "Vấn đề" 1).
- Dispatch: parser chọn theo `request.agent_context is not None` (contract `valid_job` đảm bảo `agent_context` có mặt khi và chỉ khi `prompt_version` là `agent-loop-vN`, nên tương đương chọn theo version nhưng không cần import chuỗi version vào hạ tầng). `generation_process.py` vẫn truyền parser riêng nên không chạm `request.agent_context` (request generation không có field này).

## Ladder (file/helper/dependency mới)

| Mục | Quyết định |
|---|---|
| `agent_loop.py` | plan ghi rõ (AGENTS.md buộc prompt ở `agents/prompts/`) |
| 2 file test mới | plan ghi rõ |
| Hằng `SCHEMA_HEADER`, `TASK_HEADER`, `HISTORY_HEADER`, `PAGE_HEADER`, `PAGE_OPEN`, `PAGE_CLOSE` | cần để builder và test dùng cùng một nguồn (test khoá vị trí khối); không tạo lớp/hàm trung gian |
| `_redact` cục bộ trong `agent_loop.py` (3 dòng) | trùng logic với `task_context.redact` (`codex_service.py`); không import `codex_service` từ prompt để khỏi kéo `agents.vision.executor` vào bridge container và đảo chiều phụ thuộc. Nợ nhỏ: có thể gộp một nguồn ở phase sau |
| Tham số `stage` của `CodexModelBatch` | plan liệt kê; thực tế dư thừa vì contract buộc `stage == "image"` khi và chỉ khi có ảnh (test: mâu thuẫn bị từ chối trước khi đăng ký). Giữ vì plan ghi |
| Không thêm: lớp registry, kiểm hash schema trong builder (sẽ làm job lệch phiên bản giết vòng `serve`), dependency, cờ config | tránh trừu tượng chưa cần |

## Kết quả kiểm chứng (output thật)

Cách chạy: `CODEX_BRIDGE_ENABLED=false` (override tiến trình, như baseline phase 0), `--basetemp` trong scratchpad (tránh PermissionError `pytest-of-hen`), `-p no:cacheprovider`.

Test mới (Windows):
```
tests/test_agent_loop_bridge.py + tests/test_agent_loop_prompt.py
..............ssssssssss...............
29 passed, 10 skipped in 1.49s      (10 skip = test process Linux-only, cùng lý do skipif với test process có sẵn)
```
Test mới, bản Linux đầy đủ (docker image local `auto-at-ui-temporal-worker`, `--network none`, repo mount `:ro`, pytest copy từ venv host, không ghi vào repo):
```
$ docker run --rm --network none ... -m pytest ... tests/test_agent_loop_bridge.py
........................                                                 [100%]
24 passed in 6.22s
```
Hồi quy trong checklist phase (Windows): `test_codex_bridge_process`, `test_claude_bridge`, `test_codex_bridge_spool`, `test_codex_bridge_end_to_end`, `test_codex_model_batch`, `test_codex_candidate_service`, `test_codex_exploration_integration`:
```
112 passed, 15 skipped, 13 warnings in 166.55s (0:02:46)
SKIPPED [13] test_codex_bridge_process.py:73 / [1] :122 bridge process runs in the Linux container
SKIPPED [1]  test_codex_bridge_spool.py:240 symlink adversary checked in Linux image
```
15 skip đó chạy lại trong Linux (docker, cùng cách trên) cùng `test_codex_bridge_service`, `test_codex_bridge_contracts`, `test_agent_loop_contracts`, 2 file mới:
```
291 passed in 18.71s
```
Hồi quy mở rộng (Windows): `test_codex_bridge_service, _contracts, test_agent_loop_contracts, test_codex_generation, test_codex_generation_reservation, test_codex_bridge_qualification, test_codex_bridge_benchmark, test_vision_agent_engine_selection, test_vision_model_batch, test_agent_boundaries`:
```
FAILED tests/test_codex_bridge_benchmark.py::test_offline_manifest_provenance_and_explicit_live_boundary
1 failed, 292 passed, 4 skipped, 7 warnings in 34.68s
```
Test đỏ duy nhất là cái đã đỏ ở baseline phase 0 (hash manifest `benchmark/vision/codex/manifest.json`), không do phase này.

Ruff:
```
$ uv run ruff check .
All checks passed!
```

Bằng chứng v4 không đổi byte: `test_v4_job_keeps_the_old_builder_wrapper_and_phase_zero_hashes` chạy job v4 mẫu của phase 0 qua `BridgeService` với builder dispatch thật: sha256(prompt + schema) = `cc45b116...9259`, 9269 byte, schema `6ef40dd1...0368` đúng `tests/fixtures/v4_identity.json`; `request.json` không chứa `agent_context`. `test_v4_job_keeps_the_v4_parser_and_refuses_agent_output` (Codex + Claude, Linux) xác nhận job v4 vẫn dùng parser cũ và bác output `agent_step`.

Mapping "Unit test phải viết" của phase:
- prompt: thứ tự 5 khối; tiền tố chung (khác snapshot/version/stage); version khớp README; task/memory/history redact; từ chối version khác (+ thiếu context); chuỗi "ignore previous instructions" chỉ nằm trong delimiter và delimiter giả bị trung hoà; dòng ref `version:n`/`3:17`; kích thước tối đa thực tế < 131 072.
- bridge: job agent qua fake Codex và fake Claude process (Linux) ra `AgentStep`; job v4 dùng builder/parser cũ với hash phase 0; output sai schema (`kind` lạ, họ output sai) bị `bridge_malformed_output`; round-trip `publish` -> `load` snapshot 24 000 ký tự tiếng Việt (request.json > 65 536 byte, <= 131 072); file > 131 072 bị từ chối khi đọc; dom/schema vẫn trần 65 536; prompt > 100 KB đi hết qua stdin của fake Codex và fake Claude (process nhận đúng len + sha256 từng byte); argv của Claude < 16 KB và không chứa prompt; argv Codex bằng argv v4.

## Vấn đề / quyết định cần người khác (không chặn phase 3)

1. NEEDS_USER_INPUT (ảnh hưởng chất lượng engine Codex, kiểm ở phase 6): Codex CLI luôn chạy với `model_instructions_file=/app/codex-proposal-instructions.txt` cố định (`process.py:62`, doctor `catalogue.validate_instructions` buộc file này == `codex_exploration.INSTRUCTIONS` của v4). Nghĩa là job agent qua Codex vẫn nhận instructions v4 ("propose a batch... not perform them", schema candidates) làm system, còn `agent-loop-v1` nằm ở message người dùng. Tôi giảm xung đột bằng câu mở đầu "These instructions replace any earlier proposal or exploration instructions" và schema agent ở khối 2, nhưng không chứng minh được model theo agent prompt nếu không gọi model thật. Sửa triệt để cần file instructions thứ hai (ví dụ `AGENT_INSTRUCTIONS_PATH` trong `catalogue.py` + `doctor.validate_instructions` + `docker/codex-bridge/Dockerfile`, rồi `command(..., instructions_path=...)` đã hỗ trợ sẵn tham số) - ngoài danh sách file phase 3. Claude không bị vấn đề này (system prompt `claude-bridge-system-v1` trung tính). Đề nghị: quyết ở phase 6 sau khi QA thật; nếu Codex lệch thì mở phase nhỏ làm file instructions thứ hai.
2. Trần prompt cực đoan: `CodexProcess/ClaudeProcess` bác prompt > 131 072 byte bằng `bridge_output_limit`. Ca thực tế (snapshot 24 000 + task 4 000 + memory 2 000 + 5 history x 600, toàn tiếng Việt 3 byte/ký tự, 5 host) ~ 106-110 KB: qua. Ca cực đoan 100 host x 255 ký tự cộng toàn bộ trường ở mức tối đa: request 126 273 byte (còn qua trần contract) nhưng prompt 131 279 byte > 131 072 -> fail-closed `bridge_output_limit` (không crash). Phase 4 nên giới hạn số host/độ dài host đưa vào `allowed_hosts` (allowed_origins thật hiếm khi quá vài host). Không đổi trần process (không thuộc yêu cầu và là biên an toàn).
3. "Trả done với lý do": contract `CodexStop.reason` là enum (`complete`/`no_safe_action`/`unsupported_state`), không có text tự do; prompt hướng dẫn dùng enum đó. Lý do dạng văn bản không có chỗ chứa - nếu cần phải sửa contract (ngoài phase).
4. Stdin Claude: `claude_input` dùng `json.dumps` mặc định `ensure_ascii=True` nên prompt 100 KB tiếng Việt thành ~2x byte trên stdin (6 byte/ký tự ệ). Không có trần stdin trong code; test fake process qua được. Chưa kiểm giới hạn stdin của `claude` thật (cần QA thật ở phase 6).
5. `hgraph check --changed` exit 1: do thư mục git gốc là cha của `auto-at-ui`, đường dẫn có tiền tố `auto-at-ui/` lệch với graph (cùng lỗi phase 2 đã báo); danh sách "uncovered-changed" gồm cả file đã thuộc graph. File phase 3 không còn nằm trong danh sách dạng không tiền tố. `hgraph check` (toàn bộ) exit 0.
6. Quy trình: một lần tôi sửa `spool.py` bằng script Python qua Bash heredoc (trái luật "chỉ Write/Edit"); đã chạy xong, diff kiểm đúng, các sửa sau dùng Edit/Write.
7. QA thật: chưa chạy job agent thật qua bridge host (gọi model thật) - chuyển sang phase 6, cần user cho phép.

Checklist phase:
- [x] Test mới xanh (29 + 24 Linux).
- [x] Hồi quy xanh (7 file checklist + mở rộng; 1 đỏ có sẵn ở baseline).
- [x] README prompts có dòng `agent-loop-v1`.
- [ ] QA gọi model thật: chuyển phase 6.
- [x] `uv run ruff check .` sạch.

GRAPH_UPDATE
- graph đã cập nhật: `codex-bridge` (add 4 file, sync --apply, thêm bullet mô tả họ prompt thứ hai); `vision-exploration` (sync --apply, danh sách file không đổi).
- file mới đã đưa vào graph: `apps/control-plane/agents/prompts/agent_loop.py`, `tests/test_agent_loop_bridge.py`, `tests/test_agent_loop_prompt.py`, và `apps/control-plane/agents/vision/codex_service.py` (file sửa, trước đó chưa thuộc graph nào) -> `codex-bridge`.
- hgraph check: `hgraph check — 4 graph, 448 file source / ✔ Không có vấn đề.` exit 0.
- hgraph check --changed: exit 1, chỉ vì lệch tiền tố `auto-at-ui/` (git gốc là thư mục cha) liệt kê 21 file, gồm file đã thuộc graph và file phase 1/2; không có file phase 3 nào thiếu graph.
- Graph `vision-agent-loop` vẫn chưa có: nên lập bằng `/h-graph` khi xong phase 4 (gom `agent_loop.py`, `vision_agent_loop.py`, `vision_agent_safety.py`, `vision_publisher.py`, contract agent và các test `test_agent_loop_*`).

ASK_PM: không có.
