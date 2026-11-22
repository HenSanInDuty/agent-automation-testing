STATUS: DONE

CONTEXT_CHECK
- conventions: AGENTS.md (qua docs/code-standards.md), docs/code-standards.md
- graphs: vision-agent-loop (qua hgraph brief; vision-exploration cũng phủ file)
- blast radius: 5 file bị phụ thuộc (vision_publisher, temporal_worker, 3 test) / 16 file phụ thuộc (hgraph brief)

Database: không đụng.

## Bằng chứng luật worker (CHỈ ĐỌC)
- `workers/playwright/src/vision-operations.ts:522-526` (K3): trang http(s) ngoài allowlist, agent mode chỉ cho `close_popup`/`back`, còn lại `origin_blocked`. `wait` refresh (`refresh_observation`) đi qua cùng cổng này nên bị chặn.
- `vision-operations.ts:317`: `observeDom` đòi `equivalentState(session.state, inspectState(page))`, nếu không thì `state_mismatch`. `session.state` chỉ được gán ở 867/902 (cuối một operation). Không có đường đọc-chỉ nào đồng bộ lại `session.state`; chỉ `wait` refresh làm điều đó (dòng 530-537).
- `back`/`close_popup` off-origin cũng cần `fingerprint == session.state` (dòng 541-543) nên cũng `state_mismatch` khi state cũ.

## Sửa (apps/control-plane/application/vision_agent_loop.py)
- `_observe`: khi `state_mismatch`/`state_changed_during_observation` và origin trang đã biết, KHÔNG nằm trong allowlist -> không phát `wait`; `await self.sleep(OFF_ORIGIN_RETRY_SECONDS=0.5)` rồi đọc lại `observe_dom` (tối đa `REFRESH_ATTEMPTS=3` lần như cũ). Hết lượt -> `VisionObservationUnavailable` nổi lên và phiên kết thúc với `state_mismatch` (lý do thật, không còn `origin_blocked` gây hiểu lầm).
- Trong origin, hoặc origin chưa biết (`page_unknown`): hành vi cũ (phát `wait` refresh; worker vẫn là hàng rào).
- `AgentRun.allowed_origins` (field mới, mặc định `()`), gán từ `policy.allowed_origins` lúc dựng run. Thêm `origin_allowed` vào import từ `domain.vision_agent_safety` (đã là import sẵn có của module nên không đổi quan hệ graph).
- Worker, luật origin, prompt, contract: không đổi.

## RESIDUAL RISK (cần người quyết định)
Vì worker không có đường đọc-chỉ đồng bộ lại `session.state`, retry `observe_dom` chỉ chữa được trường hợp trang quay lại đúng state đã lưu (nhiễu thoáng qua: carousel/animation). Nếu redirect đổi hẳn DOM so với state cuối của click thì mọi lần đọc đều `state_mismatch` và phiên kết thúc `state_mismatch` (rõ ràng, không treo, không vòng vô hạn). Cách chữa bền: worker cho `wait` refresh `purpose=setup` đọc-chỉ chạy off-origin (hoặc observe_dom tự resync) — thuộc phạm vi worker TS nên tôi không đụng. Chưa chứng minh được bằng live rằng r5 sẽ qua; chỉ chứng minh được bằng unit test rằng control-plane không tự giết phiên bằng `wait` bị chặn.

## Test (tests/test_vision_agent_loop.py)
- FakeWorker: (1) `errors_after_click` mô phỏng race redirect (sau click hoàn tất, `observe_dom` kế tiếp trả `state_mismatch`); (2) luật worker giờ trả operation `rejected` với `outcome_code` (như worker thật) thay vì ném RuntimeError (trước đây bị gom thành `operation_unavailable`, dễ dãi/sai hơn thật). Luật `origin_blocked` cho `wait` off-origin đã có sẵn trong `_worker_rules`.
- 4 case mới: off-origin stale read -> retry đọc-chỉ, hoàn thành `agent_done`, không có refresh wait, không `origin_blocked`, 1 lần sleep; off-origin không settle -> kết thúc `state_mismatch`, đúng 1+3 lần observe, không refresh; không có prepare tác động (click/type/wait/scroll/navigate) khi off-origin, ref bị skip `origin_blocked`; trong origin vẫn refresh bằng `wait` (đúng 1 lần). Test cũ `test_a_stale_observation_is_refreshed_with_a_read_only_wait` giữ nguyên, vẫn xanh.

### ĐỎ trên source cũ (bản source cũ = bản mới trừ khối retry off-origin; file chưa được track trong git nên dựng lại bằng xoá khối đó)
```
E  assert (None is None and 'origin_blocked' == 'agent_done' ...   # test retry off-origin
E  AssertionError: assert 'origin_blocked' == 'state_mismatch'     # test không settle
E  IndexError: list index out of range                              # test no-acting (phiên chết ở step 1)
FAILED ...::test_a_stale_read_off_origin_is_retried_read_only_not_refreshed_with_a_wait
FAILED ...::test_an_off_origin_read_that_never_settles_ends_with_its_own_reason
FAILED ...::test_no_acting_request_is_sent_while_the_page_is_off_origin
3 failed, 56 passed
```
### XANH sau sửa
```
uv run pytest tests/test_vision_agent_loop.py -q            -> 59 passed
uv run pytest tests/test_vision_agent_loop.py tests/test_vision_agent_loop_qa.py -q -> 192 passed (mốc r4 188 + 4 mới)
uv run pytest tests/test_vision_live_persistence.py -q      -> 27 passed
uv run ruff check .                                          -> All checks passed!
```
Cần Postgres cô lập 127.0.0.1:55437: tôi tự mở `r3-vision-fixture-pg` (postgres:17-alpine, chỉ localhost), đã `docker stop` (--rm) và kiểm tra không còn. Stack compose của dự án không đụng.

Không chạy được: `tests/test_vision_agent_engine_selection.py` lỗi collection do `Settings()` đọc `.env` cục bộ ("enabled Codex bridge requires explicit local tenant..."); không liên quan thay đổi này (lỗi ở thời điểm import, trước mọi test), không nằm trong mốc r4. Typecheck Python: repo không có bước typecheck trong AGENTS.md (chỉ ruff + pytest).

## Docs
`docs/vision-agent-operations.md` mục Safety/K3: thêm 3 dòng mô tả retry đọc-chỉ + lý do kết thúc `state_mismatch`. (git diff --stat của file này hiện +60 vì file đã có thay đổi chưa commit từ trước; phần tôi thêm chỉ 3 dòng.)

## Impact inventory
- Sửa: vision_agent_loop.py (logic `_observe`, field AgentRun), tests/test_vision_agent_loop.py (fake + 4 test), docs/vision-agent-operations.md.
- Caller `_observe`: chỉ `_loop` (vision_agent_loop.py:~544). `AgentRun(` chỉ dựng ở 1 chỗ. Public contract: không đổi (không đổi chữ ký ngoài field mặc định, env, API, event).
- `git diff --stat`: vision_agent_loop.py và tests/test_vision_agent_loop.py đang `??` (untracked) nên git không hiển thị diff; docs/vision-agent-operations.md như trên.

GRAPH_UPDATE
- graph đã cập nhật: không cần — không thêm/xoá file, không đổi import giữa các file (chỉ thêm symbol `origin_allowed` từ module đã được import)
- file mới đã đưa vào graph: không có
- hgraph check --changed: exit 1 vì `uncovered-changed` 48 file đổi trong working tree từ trước (codex_service.py, vision.py, config.py, dashboard... — không phải file tôi sửa). Không có dòng nào nhắc `vision_agent_loop.py` hay `test_vision_agent_loop.py` (đã thuộc graph vision-agent-loop). Cần phiên chính xử lý phần uncovered đó.
