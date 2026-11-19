---
phase: 1
title: "Contract + DB + chọn engine"
status: pending
priority: P1
owner: be-developer
qa: required
dependencies: [0]
---
## Mục tiêu
Đặt nền dữ liệu và contract cho engine `agent_loop` mà không đổi hành vi v4: cột chọn engine, bảng step log, field
API, cờ config, schema output của agent, context gửi model, cờ agent mode cho worker (regenerate TS).

## Database Impact
- `visual_exploration_sessions`: ADD `exploration_engine` String(20) NOT NULL server_default `'planner'`.
- Bảng mới `visual_agent_steps`: `id` UUID PK; `tenant_id` (TenantRecord); `project_id`; `session_id` FK theo khuôn
  `fk_visual_operation_session` (models.py:350-358); `step_index` int; `snapshot_version` int;
  `evaluation_previous_goal`, `memory`, `next_goal` Text (giới hạn độ dài ở contract); `actions` JSONB;
  `operation_ids` JSONB; `stop_reason` String(80) null; `job_id` UUID null; `created_at` timestamptz;
  UniqueConstraint(`session_id`, `step_index`).
- Migration: `migrations/versions/<rev>_add_agent_loop_engine.py`, `down_revision = "a4c6e8f01234"`.
- Rollback: `op.drop_table("visual_agent_steps")`; `op.drop_column("visual_exploration_sessions", "exploration_engine")`.
- Backfill: không (default). Lock: ADD COLUMN default hằng = metadata-only (PG ≥ 11); CREATE TABLE không khoá bảng cũ.
- Không đụng CHECK `ck_codex_job_sequence` (giữ trần 20 — K1).

## File liên quan
Tạo:
- `migrations/versions/<rev>_add_agent_loop_engine.py`
- `tests/test_agent_loop_contracts.py`, `tests/test_vision_agent_engine_selection.py` (route + application + migration)
Sửa:
- `packages/contracts/src/auto_at/contracts/codex_bridge.py`: `AgentAction` (phẳng: `kind`, `ref` `^[0-9]+:[0-9]+$`|null,
  `text`, `delta_y`, `duration_ms`, `expected_outcome`; mọi field nullable; validator Pydantic kiểm tổ hợp kind/field;
  kind ∈ {click,type,scroll,wait,back,close_popup,navigate}); `AgentStep(outcome="agent_step", evaluation_previous_goal,
  memory, next_goal, actions 1..10)`; `AgentLoopOutput` = union discriminator `outcome` của `AgentStep | CodexNeedScreenshot | CodexStop`;
  `AgentLoopContext` (task, allowed_hosts, memory ≤ 2000 ký tự, `history: tuple[str, ...]` max_length=5 mỗi chuỗi ≤ 600
  ký tự đã render sẵn, snapshot_version, snapshot text ≤ 24 000 ký tự); `CodexBridgeRequest.prompt_version` regex mở cho
  `^agent-loop-v[1-9][0-9]*$`, `agent_context` optional, `valid_job` đòi `agent_context` khi prompt agent;
  `CodexBridgeResponse.output` chấp nhận cả hai họ; `parse_agent_output`. KHÔNG thêm biến thể vào `CodexOutput`.
  `navigate` của agent luôn `ref=null` và chỉ về target_url (K2, không có field URL).
- `packages/contracts/src/auto_at/contracts/vision_worker.py`: `VisualWorkerOpen.agent_mode: bool = False` và
  `blocked_action_terms: tuple[str, ...] = ()` (≤ 40 mục, mỗi mục ≤ 40 ký tự; chỉ dùng khi agent_mode). Không nới enum
  purpose (contract đã cho `back`/`navigate` purpose explore — `VisualWorkerPrepare.references`, vision_worker.py:177-200).
- `workers/playwright/src/vision-contract.generated.ts`: regenerate (không sửa tay).
- `apps/control-plane/infrastructure/persistence/models.py`: cột + `VisualAgentStepModel` (CHECK `exploration_engine IN ('planner','agent_loop')`).
- `apps/control-plane/infrastructure/persistence/vision_unit_of_work.py`: `record_agent_step(lease, ...)` dùng `_fence(lease)`, nội dung qua
  `redact_value`; `agent_steps(session_id)` đọc theo `step_index` (phase 4 dùng cho trace, không sửa file này nữa).
- `apps/control-plane/api/v1/routes/vision.py`: `SubmitExplorationRequest.engine: Literal["planner","agent_loop"] = "planner"`;
  `ExplorationResponse.engine`; response đọc vision policy (`VisionPolicyReadResponse`, ~:95) thêm `agent_loop_enabled: bool`;
  nếu response `/trace` là model Pydantic ở route thì thêm field `agent_step` optional (mặc định null) để phase 4 điền.
- `apps/control-plane/application/vision.py`: tham số `engine`; từ chối `agent_loop` khi cờ tắt, provider không phải bridge, hoặc target ngoài `allowed_origins`.
- `apps/control-plane/application/vision_reload.py`: giữ engine của session gốc (K5).
- `apps/control-plane/config.py`, `.env.example`: `vision_agent_loop_enabled: bool = False` (`VISION_AGENT_LOOP_ENABLED`),
  `vision_agent_snapshot_chars: int = 24000` (ge=4000, le=24000).
- `apps/control-plane/domain/activity.py`: stage `agent.step`; reason code `agent_done`, `agent_stopped`, `agent_step_limit`,
  `invalid_ref`, `stale_ref`, `origin_blocked`, `sensitive_action_blocked`.

## Luồng dữ liệu của phase này
`POST /explorations {engine}` → `SubmitExplorationRequest` → `RequestVisualExploration.execute(engine)` → kiểm cờ/provider/allowlist
→ `VisualExplorationSessionModel(exploration_engine, trace_version="v4")` → outbox (không đổi) → response có `engine`.

## Convention áp dụng
`AGENTS.md` "Code organization rules": routes chỉ validate + gọi use case; `config.py` là nơi duy nhất đọc env;
contract chung ở `packages/contracts`; test focused cho mỗi thay đổi hành vi (unit cho domain/application, HTTP cho route).

## Graph liên quan
Chưa có graph. Sau phase: chạy `/h-graph` lập graph `vision-agent-loop` (contracts codex_bridge/vision_worker, routes/vision,
application/vision, vision_reload, models, vision_unit_of_work, migration) — hoặc `node C:/Users/hen/.claude/skills/h-graph/tools/hgraph.mjs check --changed` nếu graph đã có.

## Các bước thực hiện
1. Contract `codex_bridge.py` (AgentAction/AgentStep/AgentLoopOutput/AgentLoopContext, regex, valid_job, parse_agent_output).
2. Kiểm `TypeAdapter(CodexOutput).json_schema()` không đổi (so sha256 trước/sau).
3. Hàm sinh JSON schema agent `strict()` (mọi field required + nullable, `additionalProperties=false`) và kiểm qua
   `enforceable_schema` của `claude_process.py` (chỉ đọc hàm, không sửa ở phase này).
4. Contract `vision_worker.py` + regenerate TS; chạy `npm.cmd run typecheck` ở worker.
5. Migration + models + unit_of_work.
6. Route + application + reload + config + activity.
7. Test, ruff, hồi quy.

## Unit test phải viết
- `test_agent_loop_contracts.py`: AgentAction hợp lệ/không hợp lệ theo kind; ref sai format; `navigate` có ref ⇒ từ chối;
  `delta_y`/`duration_ms` âm hoặc vượt trần ⇒ từ chối; `text` tiếng Việt có dấu ở độ dài tối đa hợp lệ, +1 ⇒ từ chối;
  AgentStep 0 và 11 action bị từ chối, 1 và 10 hợp lệ; memory 2000 hợp lệ, 2001 từ chối; history 6 mục từ chối;
  parse_agent_output 3 outcome; schema agent thoả `enforceable_schema` (mẫu đúng pass, mẫu sai fail bằng jsonschema);
  sha256 schema `CodexOutput` = giá trị trong `tests/fixtures/v4_identity.json`; request `agent-loop-v1` thiếu `agent_context`
  bị từ chối; request v4 cũ vẫn hợp lệ; `blocked_action_terms` quá trần bị từ chối.
- `test_vision_agent_engine_selection.py`: không gửi `engine` → planner; `engine` lạ → 422; `agent_loop` khi cờ tắt → 4xx;
  provider không phải bridge → 4xx; target ngoài allowlist → 4xx; response có `engine`; session cũ đọc ra `engine="planner"`;
  policy response có `agent_loop_enabled`; reload giữ engine.
- DB-gated (PostgreSQL thật, `DATABASE_URL`): migration up/down (mẫu `test_vision_migration_compatibility.py`), CHECK engine;
  `record_agent_step` có fence (mất lease ⇒ từ chối), unique (session_id, step_index), nội dung chứa secret được redact,
  tenant khác không đọc được step.

## Tiêu chí xong (checklist)
- [ ] `uv run alembic upgrade head` rồi `downgrade -1` chạy sạch trên DB test; test DB-gated chạy (không skip) trong QA.
- [ ] Schema `codex-dom-v11` byte-identical (test so với `tests/fixtures/v4_identity.json`).
- [ ] Test mới xanh; hồi quy: `test_codex_bridge_contracts.py`, `test_claude_bridge.py`, `test_vision_contracts.py`,
      `test_vision_worker_contracts.py`, `test_vision_routes.py`, `test_vision_provider_submission.py`, `test_vision_reload.py`,
      `test_vision_migration_compatibility.py`, `test_codex_bridge_migrations.py` xanh.
- [ ] `uv run ruff check .` sạch; worker `npm.cmd run typecheck` sạch sau regenerate.

## Rủi ro & tín hiệu nhận biết hỏng
- Đổi union output làm đổi schema v4 → test sha256 đỏ.
- `enforceable_schema` hợp nhất `properties` sai (round 21 attempt 2) → test jsonschema mẫu hợp lệ bị từ chối.
- Regenerate TS đổi field v4 ngoài ý muốn → diff với bản sao ở `reports/phase-00/` có dòng ngoài `agent_mode`/`blocked_action_terms`.
