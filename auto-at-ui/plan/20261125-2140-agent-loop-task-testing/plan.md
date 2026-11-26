---
title: "Agent loop làm engine test theo task cho FE của người dùng"
status: in_progress
created: 2026-11-25
slug: agent-loop-task-testing
branch: feat/agent-loop-task-testing
auto_continue: false
---

# Agent loop làm engine test theo task

File này là điểm vào cho phiên mới. Đọc file này trước, rồi `docs/adr/046-agent-loop-task-testing.md` khi cần
lý do của một quyết định. Không cần đọc lại lịch sử plan cũ.

## Mục tiêu (người dùng chốt 2026-11-25)

Test được các task UI trên FE do người dùng sở hữu (dev/staging), kết quả ổn định giữa các lần chạy.
Mục tiêu cũ (">95% mọi control trên mongchiton") không còn là thước đo.

Hai quyết định của người dùng: (1) mở lại engine `agent_loop` làm engine test theo task, planner v4 giữ nguyên
và vẫn là mặc định; (2) project được đánh dấu "FE test của tôi" thì cho submit form và nhập dữ liệu test.

## Trạng thái khi dừng (2026-11-25)

- **Code chưa commit**, nằm trên nhánh `feat/agent-loop-task-testing` (43 file sửa, 14 file/thư mục mới).
  Người dùng chưa yêu cầu commit.
- **DB cục bộ đã ở migration `c8d0e2f4a6b8`**. Stack build từ `develop` không khởi động được cho tới khi
  nhánh này được merge, hoặc DB được downgrade về `b7c9d1e3f5a7` từ chính nhánh này.
- **Stack đang chạy** bằng code của nhánh (4 file compose, xem "Cách chạy"). Project "Task UI fixture" đã có
  trong tenant `demo-tenant`, policy đã bật `vision_owned_test_target`.
- Docker trên máy là engine **Kiri (WSL2)**, không phải Docker Desktop.

## Đã làm

| Việc | Ở đâu |
| --- | --- |
| Phiên agent kết thúc `completed` + `task_assessment` (achieved / not_achieved / blocked / inconclusive, checks, số liệu controller đo). Advisory, không phải verdict | `domain/vision_task_assessment.py`, `application/vision_agent_loop.py`, `vision_unit_of_work.py::finish`, `vision_results.py` |
| Đầu ra mới của agent `task_result`; planner (`codex-dom-v11`) không đổi | `packages/contracts/.../codex_bridge.py` |
| Prompt `agent-loop-v3`: đọc task thành kỳ vọng, kiểm từng hiệu ứng, xin ảnh chụp trước khi kết luận về chữ, kết thúc bằng `task_result` | `agents/prompts/agent_loop.py` + README |
| Mất một lượt gọi model / trang chưa đứng yên không giết phiên (thử lại có giới hạn) | `vision_agent_loop.py` |
| Cờ project `vision_owned_test_target`: submit form, gõ tài khoản test, thấy và gõ ô mật khẩu | migration `c8d0e2f4a6b8`, `routes/generation.py`, `vision_agent_safety.py`, worker `vision-operations.ts` / `vision-dom.ts` / `vision-locators.ts` (capability `owned-test-target-v1`) |
| Đọc lại spool khi file bị thay giữa lúc đọc (`ENODATA`, `ESTALE`, link count lạ lúc rename) | `infrastructure/codex_bridge/spool.py`, `doctor.py` (heartbeat) |
| Mở phiên worker chờ worker đang khởi động (1 + 2 + 4 giây, chỉ khi chưa kết nối được) | `infrastructure/vision_worker.py` |
| Doctor nhận diện container không có `/.dockerenv` (người dùng duyệt) | `doctor.py::inside_container` |
| Spool trên volume Linux cho engine Kiri | `docker-compose.spool-volume.yml` |
| Dashboard: panel đánh giá task, ô bật cờ FE test, nhãn engine | `apps/dashboard/app/components/vision-task-assessment*.ts(x)` và các file liên quan |
| FE mẫu cục bộ + bộ task + bộ đo | `benchmarks/targets/task-ui`, `benchmarks/task-ui/tasks.v1.json`, `benchmark/task_ui/stability.py`, `scripts/run_task_stability.py`, `docker-compose.agent-loop.yml` |

## Kết quả đo trên fixture (10 task, `claude_cli / claude-opus-5-5`)

| Lượt | Phiên | `completed` | Nhất quán | Đúng kỳ vọng | Ghi chú |
| --- | ---: | ---: | ---: | ---: | --- |
| r1 | 10 | 9 | n/a | 8 | 1 phiên hỏng do worker vừa khởi động lại; `login-failure` bị `not_achieved` sai vì snapshot không có chữ |
| r2 (2 lần/task) | 20 | 19 | 100% | 19 | 1 phiên `bridge_offline` do tranh chấp đọc heartbeat, sửa sau lượt này |
| r3 (3 task từng lỗi, code cuối) | 3 | 3 | n/a | 3 | lượt xác nhận, không phải lượt đo đầy đủ |

Mỗi phiên 25–61 giây, khoảng 3 lần gọi model. Dữ liệu ở `.pytest-artifacts/task-stability/r1|r2|r3` (gitignore).
**Chưa có lượt 10 task × nhiều lần trên code cuối.**

Kiểm thử đã chạy: `ruff` sạch; các nhóm test Python liên quan qua (715 + 359 + các nhóm nhỏ); 213 spec worker
qua; dashboard unit/typecheck/lint qua và spec dashboard qua với dữ liệu giả. Bộ test Python **chưa chạy trọn
một lượt** (bị dừng ở 87% vì giới hạn 40 phút).

## Việc tiếp theo (theo thứ tự đề xuất)

1. **Commit nhánh** khi người dùng đồng ý. Trước khi commit: chạy lại
   `python .pytest-artifacts/refresh_manifest.py` nếu còn sửa file nguồn (test
   `test_codex_bridge_benchmark.py` ghim hash trong `benchmark/vision/codex/manifest.json`), và không commit
   `benchmark/vision/visual-buttons/*.json` (hai file này bị test ghi đè khi chạy).
2. **Đo lại đầy đủ trên code cuối**: 10 task × 3–5 lần (lệnh ở "Cách chạy"). Tiêu chí "ổn định" trong bộ đo:
   `completed` ≥ 90% và nhất quán ≥ 90%.
3. **Đưa chữ trên trang vào snapshot** (cách sửa gốc cho việc agent không thấy thông báo, tiêu đề, bộ đếm).
   Hiện v3 buộc agent xin ảnh chụp, tốn thêm lượt gọi. Hướng làm: worker thu chữ nhìn thấy (role alert/status,
   heading, đoạn văn ngắn; có giới hạn; qua bộ lọc nhạy cảm) sau capability mới, chỉ ở agent mode; thêm trường
   tuỳ chọn vào `CodexDomObservation` và bỏ khỏi serialization khi rỗng để không đổi hash của v4;
   `render_snapshot` thêm phần chữ. Cần regenerate `vision-contract.generated.ts`.
4. **Chạy trên FE thật của người dùng**: tạo project, đặt allowed origin, bật cờ FE test, thử 2–3 task. Đo tài
   nguyên worker trong lúc chạy (lệnh bên dưới) để quyết định có nâng giới hạn container hay không.
5. **Nối đánh giá task sang bản nháp test Playwright** (để có verdict thật từ lần chạy deterministic). Chưa thiết kế.

## Phase

Mỗi "Việc tiếp theo" thành một file phase cùng thư mục, để skill h-cook chạy từng phase. Việc 3 tách thành hai phase
(đổi contract chung + worker TS trước, phía Python sau) nên có 6 phase; đánh số theo thứ tự chạy.

| Phase | Tên | Owner | QA | Trạng thái | Phụ thuộc |
| --- | --- | --- | --- | --- | --- |
| [01](phase-01-commit-branch.md) | Commit nhánh (cần user đồng ý) | none | skip | pending | — |
| [02](phase-02-page-text-contract-worker.md) | Chữ trên trang: contract + worker | both | required | pending | 01 |
| [03](phase-03-page-text-snapshot-prompt.md) | Chữ trên trang: `render_snapshot` + prompt | be-developer | required | pending | 02 |
| [04](phase-04-stability-remeasure.md) | Đo lại 10 task × 3–5 lần trên code cuối | none | skip | pending | 03 |
| [05](phase-05-run-on-real-fe.md) | Chạy trên FE thật của người dùng (cần user) | none | skip | pending | 01, 04 |
| [06](phase-06-design-assessment-to-playwright-draft.md) | Thiết kế assessment → bản nháp Playwright (chỉ tài liệu) | none | skip | pending | 01 |

Ánh xạ với "Việc tiếp theo": 1 → phase 01; 2 → phase 04; 3 → phase 02 + 03; 4 → phase 05; 5 → phase 06. Thứ tự đề
xuất cũ đặt đo (việc 2) trước chữ trang (việc 3); đã đảo vì "đo trên code cuối" phải sau khi code chữ trang xong.

Các "Quyết định còn chờ người dùng" bên dưới được gắn vào mục "Rủi ro/việc cần user duyệt" của phase bị ảnh hưởng
(nhãn Password: 02, 03, 05, 06; `password=...`: 03, 05, 06; giới hạn container: 04, 05; `step_deadline`: 02, 05;
audit policy route: 05, 06). Không quyết định nào được tự quyết trong phase.

## Quyết định còn chờ người dùng

- **Nhãn tiếng Anh "Password"**: ô nhập có tên là từ trong danh sách nhạy cảm vẫn bị ẩn (`validate_locator_value`
  ở cả Python và TS từ chối). Nhãn "Mật khẩu" chạy được. Bỏ từ `password` khỏi danh sách là quyết định về
  chính sách redaction, áp dụng cho mọi phiên.
- **Task viết `password=...`** bị từ chối lúc gửi (`redact_generation_request`). Hiện phải viết tài khoản thành
  câu ("mật khẩu Demo1234"). Có nới cho project FE test hay không.
- **Giới hạn container worker** (256 pids, 1 GiB): fixture đơn giản đã dùng 120 pids và 394 MiB. Có thể là
  nguyên nhân lỗi chụp ảnh ở Q4/Q5 trên trang nặng, chưa có số đo trên trang nặng.
- **Dung sai cho `step_deadline`** ở worker (xem "Lưu ý" bên dưới): đụng guard runtime.
- Route policy không ghi audit event (cả trường mới lẫn trường cũ).

## Cách chạy

```bash
# từ auto-at-ui/
export CLAUDE_BRIDGE_TOKEN_DIR=C:/Users/hen/.auto-at/claude-bridge-secrets   # đường dẫn, không phải secret
docker compose -f docker-compose.yml -f docker-compose.codex.yml \
  -f docker-compose.agent-loop.yml -f docker-compose.spool-volume.yml \
  --profile claude up -d --wait --wait-timeout 240

# token bridge hết hạn hoặc bị thu hồi (bridge_model_unavailable):
uv run python scripts/export_claude_bridge_token.py C:/Users/hen/.auto-at/claude-bridge-secrets

# header đăng nhập cục bộ cho script (auth_mode=local); tạo lại nếu .pytest-artifacts bị dọn:
# .pytest-artifacts/accuracy-local-headers.json =
#   {"X-Tenant-Id": "demo-tenant", "X-Actor-Id": "task-stability", "X-Actor-Roles": "tenant_admin"}

# đo độ ổn định (mỗi phiên gọi model thật qua bridge)
uv run python scripts/run_task_stability.py run --project "Task UI fixture" \
  --base-url http://task-target:7300 --repeat 5 --out .pytest-artifacts/task-stability/r4
uv run python scripts/run_task_stability.py report --out .pytest-artifacts/task-stability/r4

# đỉnh tài nguyên của worker
docker exec auto-at-ui-playwright-worker-1 sh -c \
  'cat /sys/fs/cgroup/pids.peak /sys/fs/cgroup/memory.peak; cat /sys/fs/cgroup/memory.events'
```

Test trên host:

```bash
docker run --rm -d --name agent-task-fixture-postgres -e POSTGRES_PASSWORD=vision-fixture-only \
  -p 127.0.0.1:55437:5432 postgres:17-alpine          # thiếu container này thì test DB tự skip
CODEX_BRIDGE_ENABLED=false uv run pytest tests/test_vision_agent_task_assessment.py \
  tests/test_vision_agent_loop.py -q --basetemp=.pytest-artifacts/tmp-x -p no:cacheprovider
cd workers/playwright && npm.cmd run typecheck && npx.cmd playwright test src/vision-agent-mode.spec.ts
```

Dùng trên dashboard: tab Vision, chọn engine "Agent loop (task testing)", nhập URL + task. Bật cờ FE test ở form
policy của project ("This is a test environment I own").

## Lưu ý dễ vấp

- `tests/test_vision_page_batch.py` **dao động có sẵn** trên host Windows (`invalid_step_deadline`): HEAD trượt
  4/21, nhánh này 9/21. Worker so `step_deadline` với `Date.now()` không dung sai, mà đồng hồ Node trên máy này
  chậm hơn Python 0,2–10 ms tuỳ tiến trình. Trong container Linux không gặp. Đừng coi là hồi quy nếu chưa A/B
  với HEAD.
- Bộ test Python đầy đủ mất hơn 40 phút trên máy này, lâu hơn khi stack đang chạy.
- `npx.cmd playwright test -g` với mẫu có dấu cách hoặc `|` làm hỏng shim trên Windows; dùng một từ.
- Sau `up`, đợi vài giây rồi mới gửi phiên: `playwright-worker` không có healthcheck.
- Đừng tạo git worktree trong thư mục tạm của phiên: nó bị dọn giữa chừng.
- Phiên agent cũ trong DB vẫn có dạng `unavailable / agent_done`, không có `task_assessment`.

## Tài liệu liên quan

- Quyết định và phạm vi: `docs/adr/046-agent-loop-task-testing.md`
- Plan gốc của engine (đã ghi chú mở lại): `plan/20261119-2212-browser-agent-loop/plan.md`
- Plan độ chính xác cũ (vẫn dừng): `plan/09112026103202-vision-accuracy-loop/README.md`
- FE mẫu: `benchmarks/targets/task-ui/README.md` (tài khoản test `demo` / `Demo1234`, trang `/broken` cố ý lỗi)
