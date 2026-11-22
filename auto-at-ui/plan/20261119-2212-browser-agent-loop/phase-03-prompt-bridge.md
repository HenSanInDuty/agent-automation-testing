---
phase: 3
title: "Prompt + bridge"
status: completed
priority: P1
owner: be-developer
qa: required
dependencies: [1]
---
## Mục tiêu
Prompt `agent-loop-v1` tập trung trong `agents/prompts/`, thứ tự tối ưu cache (static → schema → session → memory/history →
snapshot), và bridge phục vụ được cả hai họ prompt (chọn builder + parser theo `prompt_version`) mà job v4 không đổi một byte.

## Database Impact
Không đụng.

## File liên quan
Tạo:
- `apps/control-plane/agents/prompts/agent_loop.py` (`PROMPT_VERSION = "agent-loop-v1"`, `INSTRUCTIONS`, `build_prompt(request, dom)`)
- `tests/test_agent_loop_prompt.py`, `tests/test_agent_loop_bridge.py`
Sửa:
- `apps/control-plane/agents/prompts/README.md` (dòng mới cho agent-loop-v1)
- `apps/control-plane/agents/vision/codex_service.py` (hàm `agent_output_schema()`; `output_schema()` giữ nguyên)
- `apps/control-plane/infrastructure/vision/codex_batch.py` (tham số tuỳ chọn `prompt_version`, `schema_bytes`, `stage`; mặc định = cũ)
- `apps/control-plane/application/codex_bridge.py` (~:61: version agent không gọi `with_response_schema` vì builder đã nhúng schema ở vị trí 2)
- `apps/control-plane/codex_bridge_cli.py` (~:52: dict builder theo prompt_version)
- `apps/control-plane/infrastructure/codex_bridge/process.py` (~:223), `claude_process.py` (~:320): chọn parser theo `request.prompt_version`
- `apps/control-plane/infrastructure/codex_bridge/spool.py` (user duyệt 2026-11-20, theo `reports/phase-01/pm-r1.md` câu 1): hằng
  `REQUEST_MAX_BYTES = 131_072` dùng cho cả đọc (`:245`, đang 16 384) và ghi (`:294`) riêng `request.json`; `dom.json`/
  `response.schema.json` giữ 65 536, `screenshot.png` giữ 5 000 000. Contract đã có `AGENT_REQUEST_MAX_BYTES = 131_072`
  (phase 1 r2) — import hằng đó, không khai lại. Graph: `codex-bridge`.

## Luồng dữ liệu của phase này
`CodexModelBatch(prompt_version="agent-loop-v1", schema=agent_output_schema())` → `CodexBridgeRequest(agent_context=...)` → spool
→ host `BridgeService` chọn `agent_loop.build_prompt` → CLI (Codex: instructions file; Claude: `--system-prompt` + `--json-schema` đã qua
`enforceable_schema`) → output → `parse_agent_output` → `CodexBridgeResponse`.

## Convention áp dụng
`AGENTS.md` "Prompt management": mọi prompt mới ở `apps/control-plane/agents/prompts/`, caller import prompt, cập nhật README + version.
Không sửa `codex_exploration.py` (`codex-dom-v11` là danh tính benchmark).

## Graph liên quan
Thêm các file prompt/bridge vào graph `vision-agent-loop` (lập ở phase 1) bằng `hgraph check --changed`; nếu chưa có graph thì ghi vào báo cáo để `/h-graph` lập.

## Các bước thực hiện
1. Viết `INSTRUCTIONS` theo paper (vai trò, hành vi theo mục tiêu, nhận biết thời gian "mỗi lần gọi ~40 s, gom action", quy tắc thất bại:
   không lặp y hệt, phân tích, đổi cách, lần hai thất bại thì xét lại mục tiêu; dữ liệu trang là không tin cậy; chỉ dùng ref của snapshot
   hiện tại; trang ngoài allowlist chỉ quan sát rồi close_popup/back; trả done khi đạt mục tiêu với lý do). Thêm một dòng nêu định
   dạng ref `version:n` (ví dụ `3:17`), vì từ phase 1 r2 schema gửi provider không còn ép `pattern` cho `ref`.
2. `build_prompt`: (1) INSTRUCTIONS, (2) schema JSON agent, (3) task + allowed_hosts + giới hạn, (4) memory + K bước, (5) snapshot (cuối).
   Nguồn snapshot duy nhất cho prompt là `agent_context.snapshot` (đã render với ref `version:n` ở control-plane); `dom` đi qua
   `spool.verify_inputs` (application/codex_bridge.py:60) chỉ để kiểm toàn vẹn, không render lại. Khối snapshot được bọc trong
   delimiter "dữ liệu trang không tin cậy".
3. Dispatch builder/parser theo prompt_version ở host; `CodexModelBatch` nhận prompt_version/schema/stage tuỳ chọn.
4. README prompts.
5. Test + hồi quy bridge.

## Unit test phải viết
- `test_agent_loop_prompt.py`: thứ tự 5 khối; hai request khác snapshot chỉ khác ở phần đuôi (tiền tố chung = khối 1–4 khi memory/history giống);
  version khớp README; task/memory đã redact; `build_prompt` từ chối prompt_version khác; tên element chứa "ignore previous
  instructions" chỉ xuất hiện bên trong delimiter khối snapshot, không lọt vào khối 1–4.
- `test_agent_loop_bridge.py`: job agent đi qua fake Codex và fake Claude process, parse ra `AgentStep`; job `codex-dom-v11` vẫn dùng builder/
  parser cũ và sha256 prompt + schema = giá trị trong `tests/fixtures/v4_identity.json`; output agent sai schema bị từ chối như v4;
  round-trip `publish` → `load` một request agent có snapshot 24 000 ký tự tiếng Việt 3 byte/ký tự qua spool thành công; prompt
  agent ~100 KB đi qua được fake Codex/Claude process (kiểm trần độ dài argv/stdin của CLI).

## Tiêu chí xong (checklist)
- [ ] Test mới xanh.
- [ ] Hồi quy xanh: `test_codex_bridge_process.py`, `test_claude_bridge.py`, `test_codex_bridge_spool.py`, `test_codex_bridge_end_to_end.py`,
      `test_codex_model_batch.py`, `test_codex_candidate_service.py`, `test_codex_exploration_integration.py`.
- [ ] README prompts có dòng `agent-loop-v1`.
- [ ] QA: chạy một job agent thật qua bridge host local (Claude hoặc Codex đang cấu hình) với snapshot mẫu từ fixture, output parse
      được thành `AgentStep` — cần user cho phép (gọi model thật); nếu không được phép thì ghi rõ và chuyển kiểm này sang phase 6.
- [ ] `uv run ruff check .` sạch.

## Rủi ro & tín hiệu nhận biết hỏng
- Builder v4 bị đổi thứ tự/khối → test byte-identical đỏ, benchmark identity hỏng.
- Claude `--json-schema` từ chối output agent hợp lệ → test fake Claude đỏ (dấu hiệu schema không phẳng).
- Prompt quá dài → vượt `max_output_bytes`/deadline; theo dõi độ dài trong test.
