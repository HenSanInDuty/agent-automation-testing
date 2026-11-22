STATUS: ESCALATE

# Phase 1 - vòng sửa r2 (be-developer-junior, browser-agent-loop)

Code và test của vòng r2 đã xong và xanh, trừ đúng các mục nêu dưới đây. Dừng vì hai lý do:
1. `hgraph check --changed` exit 1 với `uncovered-changed` cho 13 file, gồm cả `codex_bridge.py`. File này đã có trong `docs/graphs/vision-exploration.md` (brief cũng gán nó vào graph này), nên lỗi nằm ở cách hgraph khớp đường dẫn (git toplevel là `agent-at/`, graph ghi đường dẫn từ `auto-at-ui/`). Đây là lỗi tool đã ghi ở r1. Sửa không nằm trong phạm vi file được phép (cần sửa graph hoặc hgraph).
2. 10 test trong `tests/test_qa_phase01_edges.py::test_qa_ref_bad` đỏ vì đúng hành vi mới (ref không còn bị chặn ở parse). Theo prompt, không sửa file đó.

## CONTEXT_CHECK
- conventions: `AGENTS.md` (đọc nguyên văn: Code organization rules, Required checks, Assistant token budget). `docs/code-standards.md` chỉ là chỉ mục trỏ về AGENTS.md. `docs/api-conventions.md` không tồn tại (prompt cho bỏ qua, không bịa convention).
- graphs: `vision-exploration` (đọc frontmatter và file list; có `codex_bridge.py` role other). `codex-bridge` (brief liệt kê là graph liên quan, chưa mở rộng ở vòng này).
- blast radius (hgraph brief, depth 2): 0 file bị phụ thuộc trực tiếp; 7 file nền (`codex_bridge.py` và test liên quan). Caller của `AgentRef`/`AGENT_REF_PATTERN`/`AGENT_REQUEST_MAX_BYTES` ngoài 2 file phạm vi: không có (grep, loại trừ `.venv` và `plan/`).

## Impact inventory

### Database
Database: không đụng.

### File & contract
| File | Thay đổi | Lý do |
|---|---|---|
| `packages/contracts/src/auto_at/contracts/codex_bridge.py` | +8/-1 (vòng r2) | nới `AgentRef`, xuất `AGENT_REF_PATTERN`, thêm `AGENT_REQUEST_MAX_BYTES` + validator trần byte |
| `tests/test_agent_loop_contracts.py` | +~70/-~6 (ước lượng từ edit; file untracked nên numstat không có) | sửa test ref, thêm test trần 24/25 ký tự, test snapshot 24 000 ký tự tiếng Việt, cập nhật schema bad/good case |

Không sửa file nào khác. Không regenerate. Không migration. Không commit.

Public contract đụng tới:
- `AgentRef`: từ `Annotated[str, Field(pattern=..., max_length=24)]` thành `Annotated[str, Field(min_length=1, max_length=24)]`. Schema agent gửi provider mất `pattern` (chỉ nằm trong họ agent; `CodexOutput` không đổi).
- Mới: `AGENT_REF_PATTERN`, `AGENT_REQUEST_MAX_BYTES`.
- `CodexBridgeRequest.valid_job`: thêm một điều kiện, chỉ khi `agent_context` có mặt.

Ghi chú về `min_length=1`: prompt chỉ yêu cầu `max_length=24`. Tôi thêm `min_length=1` theo quyết định PM r1 Câu 2 (ref rỗng vẫn bị từ chối ở contract). Nếu lead muốn đúng từng chữ prompt thì bỏ một tham số.

Test hiện có đang phủ: `tests/test_agent_loop_contracts.py` (76 test cũ + mới), `tests/test_qa_phase01_edges.py`, `tests/test_codex_bridge_contracts.py`, `tests/test_claude_bridge.py`, `tests/test_vision_agent_engine_selection.py`.

## Thay đổi chi tiết

### codex_bridge.py
- `:210-211` (+2): hằng `AGENT_REQUEST_MAX_BYTES = 131_072` kèm comment.
- `:264-265` (+2) trong `valid_job`:
  ```python
  if is_agent and len(canonical_bytes(self)) > AGENT_REQUEST_MAX_BYTES:
      raise ValueError("agent request exceeds byte limit")
  ```
  Request v4 (`is_agent` = False) không đi qua điều kiện này.
- `:373-376` (+4/-1): comment hai dòng, `AGENT_REF_PATTERN = r"^[0-9]+:[0-9]+$"`, và `AgentRef = Annotated[str, Field(min_length=1, max_length=24)]` thay dòng cũ có `pattern=`.
- `fields_match_kind` và rule `navigate` (ref phải null) không đổi. `ref` vẫn nullable.

### tests/test_agent_loop_contracts.py
- Import thêm `AGENT_REF_PATTERN`, `AGENT_REQUEST_MAX_BYTES`, `AGENT_SNAPSHOT_MAX_CHARS`.
- Thay `test_agent_action_rejects_malformed_refs` bằng:
  - `test_agent_action_parses_off_format_refs_within_length_and_leaves_format_to_the_domain`: 12 ref sai regex (có `"3:1\n"`, `"e_"+"a"*21`) đều parse được, độ dài ≤ 24, `re.fullmatch(AGENT_REF_PATTERN)` là None.
  - `test_agent_action_rejects_refs_longer_than_24_or_empty`: 25 ký tự (`"1"*12 + ":" + "2"*12`), `"e_"+"a"*32`, `"1"*30`, `""` đều bị từ chối.
  - `test_agent_action_ref_exactly_24_characters_is_accepted`: đúng 24 ký tự được nhận.
  - `test_agent_ref_pattern_accepts_version_colon_number_refs`: `3:1`, `12:345`, `0:0` khớp pattern.
- `test_agent_schema_accepts_what_pydantic_accepts_and_rejects_what_it_rejects`: bỏ `not-a-ref` khỏi danh sách bad (giờ schema và parser đều nhận), chuyển sang danh sách good kèm comment; bad mới là ref 25 ký tự `"9"*25`.
- `test_agent_schema_is_strict_flat_and_satisfiable_by_enforceable_schema`: thêm khẳng định ref schema không có `pattern` và có `{type string, minLength 1, maxLength 24}` trong `anyOf`.
- Thêm `test_agent_request_with_24000_vietnamese_snapshot_chars_is_within_the_byte_ceiling`: snapshot 24 000 ký tự 'ế' (72 000 byte) có kích thước canonical trong (72 000, 131 072]. Hợp lệ.
- Thêm `test_agent_request_is_refused_when_its_canonical_bytes_exceed_the_ceiling`: snapshot 24 000 'ế' + 100 host 255 'ế' (76 500 byte) → `ValueError` khớp "byte limit". Cùng snapshot với host ASCII → hợp lệ. Dữ liệu này kiểm được cả hai phía và chứng minh giới hạn đếm byte, không đếm ký tự.
- Thêm `test_v4_request_is_not_subject_to_the_agent_byte_ceiling`: request v4 vẫn hợp lệ, dưới trần.
- Giữ nguyên, vẫn xanh: `test_codex_output_schema_sha256_matches_the_phase_zero_baseline` (sha256 + bytes của `CodexOutput`), `test_v4_prompt_schema_and_request_hash_match_the_phase_zero_baseline` (`codex-dom-v11` khớp `tests/fixtures/v4_identity.json`, request hash v4 `7d124f62...` không đổi).

## Output thật

### pytest (lệnh yêu cầu, basetemp trong scratchpad)
Lệnh: `CODEX_BRIDGE_ENABLED=false uv run pytest tests/test_agent_loop_contracts.py tests/test_vision_agent_engine_selection.py tests/test_qa_phase01_edges.py tests/test_codex_bridge_contracts.py tests/test_claude_bridge.py -q -p no:cacheprovider --basetemp=<scratchpad>/basetemp-r2b`

Kết quả (log đầy đủ: `C:\Users\hen\AppData\Local\Temp\claude\920469b1ee901aec\b31c51c4-3d83-413c-9fc7-991602ceba04\scratchpad\pytest-r2b.log`):
```
FAILED tests/test_qa_phase01_edges.py::test_qa_ref_bad[1] - Failed: DID NOT R...
FAILED tests/test_qa_phase01_edges.py::test_qa_ref_bad[1:] - Failed: DID NOT ...
FAILED tests/test_qa_phase01_edges.py::test_qa_ref_bad[:2] - Failed: DID NOT ...
FAILED tests/test_qa_phase01_edges.py::test_qa_ref_bad[a:b] - Failed: DID NOT...
FAILED tests/test_qa_phase01_edges.py::test_qa_ref_bad[ 1:2] - Failed: DID NO...
FAILED tests/test_qa_phase01_edges.py::test_qa_ref_bad[1:2 ] - Failed: DID NO...
FAILED tests/test_qa_phase01_edges.py::test_qa_ref_bad[1:2\n] - Failed: DID N...
FAILED tests/test_qa_phase01_edges.py::test_qa_ref_bad[1:2:3] - Failed: DID N...
FAILED tests/test_qa_phase01_edges.py::test_qa_ref_bad[-1:2] - Failed: DID NO...
FAILED tests/test_qa_phase01_edges.py::test_qa_ref_bad[\u0661:\u0662] - Faile...
10 failed, 263 passed, 6 warnings in 38.20s
```
Lần chạy đầu (trước sửa E501) cho cùng 10 fail, 263 pass.

Phân tích 10 test đỏ: đều là `test_qa_ref_bad`, do QA viết theo hành vi cũ "ref sai regex bị chặn ở parse". Hành vi mới theo PM r1 Câu 2 là chủ đích: ref sai format parse được, domain trả `invalid_ref` (phase 4). Hai ca `""` và `"1:"+"9"*30` (32 ký tự) vẫn bị chặn (min_length và max_length). Cần lead quyết: cập nhật test QA sang kỳ vọng mới (chỉ chặn độ dài/rỗng, còn format kiểm ở domain), hoặc giữ hành vi cũ và bỏ nới `AgentRef`. Tôi không sửa file QA theo prompt.

### Test liên quan đã xanh (trong 263 passed)
- Schema `codex-dom-v11` và `CodexOutput`: sha256 và bytes khớp fixture.
- `enforceable_schema(agent_loop_output_schema()) == schema`: xanh.

### ruff
Lệnh: `uv run ruff check . --output-format concise`
```
All checks passed!
```
(Lần chạy đầu có 1 lỗi E501 ở comment tôi viết, đã sửa; file phase-00 `v4_identity.py` không còn báo lỗi trong lần chạy này.)

### hgraph
- `node C:/Users/hen/.claude/skills/h-graph/tools/hgraph.mjs check` → exit 0:
  ```
  hgraph check — 4 graph, 442 file source
  ✔ Không có vấn đề.
  ```
- `node C:/Users/hen/.claude/skills/h-graph/tools/hgraph.mjs check --changed` → exit 1:
  ```
  File vừa đổi: 18
  ✖ [uncovered-changed] file vừa đổi/mới nhưng chưa thuộc graph nào
    apps/control-plane/api/v1/routes/vision.py
    apps/control-plane/application/vision.py
    apps/control-plane/application/vision_reload.py
    apps/control-plane/config.py
    apps/control-plane/domain/activity.py
    apps/control-plane/infrastructure/persistence/models.py
    apps/control-plane/infrastructure/persistence/vision_unit_of_work.py
    packages/contracts/src/auto_at/contracts/codex_bridge.py
    packages/contracts/src/auto_at/contracts/vision_worker.py
    tests/test_vision_handoff_repository.py
    tests/test_vision_policy_persistence.py
    tests/test_vision_policy_routes.py
    workers/playwright/src/vision-contract.generated.ts
  ```
  Danh sách này giống hệt r1 (đã nêu trong `be-developer-r1.md`). Vòng r2 không thêm file mới và không đổi quan hệ import, nên không phát sinh lỗi mới. Lỗi là do đường dẫn: các file này đã có trong graph với đường dẫn không tiền tố (ví dụ `apps/control-plane/config.py`), còn git trả về đường dẫn có tiền tố `auto-at-ui/`.

## GRAPH_UPDATE
- graph đã cập nhật: không cần trong vòng r2 (không thêm/xoá file, không đổi quan hệ import).
- file mới đã đưa vào graph: không có.
- `hgraph check --changed`: exit 1 (lỗi khớp đường dẫn của hgraph, ghi ở ESCALATE). `hgraph check` (đầy đủ): exit 0.

## ESCALATE
- lý do: (1) `hgraph check --changed` exit 1 do lỗi khớp đường dẫn của hgraph (tiền tố `auto-at-ui/`), không do thiếu graph. Muốn exit 0 phải sửa `docs/graphs/*.md` hoặc hgraph, cả hai ngoài phạm vi file được phép. (2) 10 test QA `test_qa_ref_bad` đỏ vì đổi hành vi có chủ đích, cần lead quyết định.
- đã tìm được: `docs/graphs/vision-exploration.md` (file list có `codex_bridge.py`); output `hgraph-changed-r2.log` (13 file uncovered, giống r1); `tests/test_qa_phase01_edges.py:64-68` (10 ca đỏ).
- đề xuất: chuyển cho lead để (a) cho phép sửa cách khớp đường dẫn của hgraph (hoặc lập lại graph theo đường dẫn từ `agent-at/`), rồi chạy lại `hgraph check --changed`; (b) quyết định cập nhật `test_qa_ref_bad` sang hành vi mới (ref sai format được parse, chỉ chặn rỗng/quá 24 ký tự), hoặc bỏ nới `AgentRef`.

## Ghi chú rủi ro (không chặn vòng này)
- `spool.py` vẫn đọc `request.json` tối đa 16 384 byte (`apps/control-plane/infrastructure/codex_bridge/spool.py:245`). Request agent có snapshot lớn vượt 16 KB sẽ không load được cho tới khi phase 3 nâng hằng số đọc/ghi (PM r1 Câu 1). Vòng này không đụng spool, đúng phạm vi.
- PM r1 (Câu 1) có hai khuyến nghị: thêm validator ở phase 1 (vòng r2, như prompt yêu cầu) và "khuyến nghị: cả hằng + validator ở phase 3". Tôi làm theo prompt r2 (validator ở phase 1). Nếu lead muốn chuyển sang phase 3 thì chỉ cần bỏ đoạn `valid_job` và test byte ceiling, còn lại không đổi.
- `AGENT_REF_PATTERN` dùng `^...$` với `re.fullmatch`: `"3:1\n"` không khớp (đã có test). Phase 4 phải dùng fullmatch chứ không dùng `re.match` + `$`.

## Dọn dẹp
- Không còn tiến trình nào mở. Không docker, không server, không DB. Chỉ có `uv run pytest`, `uv run ruff`, `node hgraph` đã thoát.
- Log ở scratchpad: `pytest-r2.log`, `pytest-r2b.log`, `ruff-r2.log`, `hgraph-check-r2.log`, `hgraph-changed-r2.log`.
- Không commit. Không chạy migration. Không sửa `.env`.
