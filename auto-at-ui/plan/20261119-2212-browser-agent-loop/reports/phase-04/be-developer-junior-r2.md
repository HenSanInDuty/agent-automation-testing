STATUS: DONE

# be-developer-junior r2 (phase 4): agent_steps cho /trace production

Phạm vi: đúng 3 file user cho phép. Không sửa route, schema, migration, contract. Không chạy migration lên DB thật. Không commit. Không đụng benchmark.

## CONTEXT_CHECK
- conventions: `docs/code-standards.md` (chỉ là mục lục trỏ về `AGENTS.md`, đọc nguyên văn) và `AGENTS.md` (Code organization rules: infrastructure implement port, route không gọi DB trực tiếp, test cùng phase). `docs/api-conventions.md` không tồn tại. Không có CONVENTION_ISSUE.
- graphs: `vision-exploration` (repositories.py, vision_unit_of_work.py), `vision-agent-loop` (tests/test_vision_agent_loop.py)
- blast radius: 55 file phụ thuộc (depth 2) theo `hgraph brief`. Thay đổi là thêm method và đổi nơi gọi bên trong UoW, không đổi chữ ký public nào.

## Impact inventory

### Database
Database: không đụng. Chỉ đọc bảng `visual_agent_steps` đã có (không ALTER, không index mới). Không backfill, không lock. Consumer đọc bảng này: `SqlAlchemyVisualTraceUnitOfWork.agent_steps` (đã có), `VisionResults._agent_steps` qua route `_results` (nay có method thật).

### File và contract
| File | Thao tác | Lý do |
|---|---|---|
| `apps/control-plane/infrastructure/persistence/repositories.py` | sửa | thêm import `VisualAgentStepModel` và method `SqlAlchemyVisualTraceRepository.agent_steps(scope)` (query chuyển từ UoW sang, cùng `_scope` + `order_by(step_index)`) |
| `apps/control-plane/infrastructure/persistence/vision_unit_of_work.py` | sửa | `agent_steps` mở session rồi gọi `SqlAlchemyVisualTraceRepository(session).agent_steps(scope)`, vẫn trả list `_detached(...)` như cũ |
| `tests/test_vision_agent_loop.py` | sửa | bỏ dòng gán tay `repo.agent_steps = run.uow.agent_steps`, dùng `SqlAlchemyVisualTraceRepository(db)` thật trong `VisionResults`; thêm `test_trace_repository_reads_agent_steps_in_order_and_only_for_its_scope` |

Caller của `agent_steps` (grep thật): `application/vision_results.py:31` (qua getattr trên trace repo), `infrastructure/persistence/vision_unit_of_work.py` (định nghĩa), `tests/test_vision_agent_engine_selection.py` (nhiều chỗ, qua UoW), `tests/test_vision_agent_loop.py:470,778,~847` (qua UoW). Không đổi chữ ký của UoW, nên các caller này không đổi.

Route `apps/control-plane/api/v1/routes/vision.py:738` đã truyền `SqlAlchemyVisualTraceRepository(session)` vào `VisionResults`, nên không cần sửa route. Sau thay đổi, `getattr(self.trace, "agent_steps", None)` tìm thấy method thật và `agent_step` xuất hiện trong `/trace` của session agent_loop.

Kiểu trả về: repo trả list ORM `VisualAgentStepModel` (đồng nhất với các method repo khác). UoW vẫn trả bản `SimpleNamespace` detached như trước. Đây là chỗ khác duy nhất so với "cùng kiểu" và chỉ có ở tầng repo nội bộ.

Test hiện có phủ vùng này: `test_vision_agent_engine_selection.py` (scope tenant/project/session, thứ tự, migration) và `test_vision_agent_loop.py` (renderer, processor, trace). Phần mới: repo SQL thật qua `VisionResults` cho agent_loop và planner, và repo scope theo tenant/project.

## Thay đổi chi tiết

Repo, method mới (`repositories.py`, trước `snapshot`):
```python
def agent_steps(self, scope: VisualSessionScope) -> list[VisualAgentStepModel]:
    return list(self._session.scalars(
        select(VisualAgentStepModel).where(
            *self._scope(VisualAgentStepModel, scope),
        ).order_by(VisualAgentStepModel.step_index)
    ))
```

UoW (`vision_unit_of_work.py`): thân `agent_steps` còn một vòng `[self._detached(step) for step in SqlAlchemyVisualTraceRepository(session).agent_steps(scope)]` trong `transactional_session`. Import `select` của UoW vẫn cần (còn dùng ở dòng ~286), nên không xoá import.

Test: xem file. Kỳ vọng DONE là step thứ 4 khi chạy 3 bước `wait()` + DONE (đúng với test ba bước hiện có: DONE cũng ghi một step).

## Kiểm tra (output thật)

Lệnh đầu tiên không có biến môi trường bị lỗi collection ở `test_vision_results.py` và `test_vision_agent_engine_selection.py`: `pydantic ValidationError: enabled Codex bridge requires explicit local tenant...` (config.py:182, import `main.py`). Đây là thiết lập môi trường, không liên quan thay đổi. Chạy lại với `CODEX_BRIDGE_ENABLED=false` (đúng như leader-r1 đã dùng).

1. `uv run pytest tests/test_vision_agent_loop.py -q` (lần 1) → `1 failed, 50 passed` (test mới kỳ vọng sai `[1,2,3]`, đã sửa thành `[1,2,3,4]`).
2. `uv run pytest tests/test_vision_agent_loop.py -q -k trace` → `2 passed, 49 deselected in 4.80s`
3. `uv run pytest tests/test_vision_agent_loop.py tests/test_vision_agent_safety.py tests/test_vision_agent_loop_qa.py -q -p no:cacheprovider` → `236 passed, 1 warning in 123.87s (0:02:03)`
4. `CODEX_BRIDGE_ENABLED=false uv run pytest tests/test_vision_results.py tests/test_vision_live_persistence.py tests/test_vision_agent_engine_selection.py -q -p no:cacheprovider` → `79 passed, 6 warnings in 179.97s (0:02:59)`
5. Sau khi sửa định dạng (wrap dòng E501), chạy lại `-k trace` → `2 passed, 49 deselected in 4.82s`. Phần đó chỉ là định dạng, không đổi logic.
6. `uv run ruff check .` lần 1 → `E501 Line too long (101 > 100) tests\test_vision_agent_loop.py:821`. Đã wrap lại. Lần 2 → `All checks passed!` (exit 0).
7. `hgraph sync vision-agent-loop` và `hgraph sync vision-exploration` (dry run, không `--apply`): không có file mới và không đổi quan hệ import giữa các file trong graph, nên không apply. Dry run báo lệch có sẵn không do phase 4 (xem Ghi chú).
8. `hgraph check` → `hgraph check — 5 graph, 454 file source`, `✔ Không có vấn đề.`, exit 0.
9. `hgraph check --changed` → exit 1. Đối chiếu 24 dòng `uncovered-changed`, tất cả có tiền tố `auto-at-ui/` (lỗi đã biết của phase trước). Không có dòng nào thiếu tiền tố ngoài dòng hướng dẫn.
10. `git status --short -- benchmark` → rỗng.

Dọn tiến trình: không mở server, worker hay docker nào. Chỉ chạy pytest và hgraph đơn lẻ, đã kết thúc.

## GRAPH_UPDATE
- graph đã cập nhật: không cần. Không thêm/xoá file, không đổi quan hệ import giữa các file trong graph (repositories.py và vision_unit_of_work.py đã import `repositories` và `models` trước đó). Dry run `hgraph sync` không đề xuất thay đổi do phase này.
- file mới đã đưa vào graph: không có
- hgraph check --changed: exit 1, chỉ các dòng `uncovered-changed` có tiền tố `auto-at-ui/` đã biết (24 dòng). Output thật ở mục 9 phía trên.

## Ghi chú và rủi ro còn lại
- `git diff --stat` của `vision_unit_of_work.py` (+42) gồm cả thay đổi của phase 1-3 đang nằm trong working tree. Phần của phase 4 chỉ là khối `agent_steps` (đã mô tả). Không revert gì.
- Đã dùng `CODEX_BRIDGE_ENABLED=false` để chạy các test import `main.py`. Không ghi file cấu hình nào.
- Dry run `hgraph sync vision-exploration` báo 3 file không còn thuộc graph (`infrastructure/persistence/models.py`, migration `b7c9d1e3f5a7`, `packages/contracts/.../codex_bridge.py`) và nhiều file ngoài đang gọi vào graph. Đây là lệch có sẵn từ các phase trước, không do phase 4, và không nằm trong 3 file được phép sửa. Không tự sửa. Cần `hgraph sync` có chủ đích do leader quyết.
- Vòng đời session của ORM: `_agent_steps` đọc các cột trên list ORM sau khi repo đóng query trong cùng session của request. Đường đọc không commit, nên không có expire. Không xác minh được hết vòng đời session trong `routes/vision.py` vì không đọc phần đó (đúng phạm vi cho phép).

## Phụ thuộc phase 5
`agent_step` trong `/trace` đã chạy được với repo SQL thật (route không đổi). Phase 5 có thể dùng `agent_step` từ `/trace`.
