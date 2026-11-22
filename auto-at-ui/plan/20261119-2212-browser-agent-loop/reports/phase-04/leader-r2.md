STATUS: PASS

# Leader r2 phase 4 - Van de 1 (agent_step trong /trace production)

BLOCKING: khong co.

Kiem:
- repositories.py: SqlAlchemyVisualTraceRepository.agent_steps dung _scope (tenant_id, project_id, session_id; repositories.py:908) va order_by(step_index). Dung.
- vision_unit_of_work.py: agent_steps mo transactional_session, goi repo, tra list _detached(step) nhu cu; chu ky khong doi nen caller UoW khong vo.
- Route vision.py:738 _results truyen SqlAlchemyVisualTraceRepository(session) -> getattr(self.trace,"agent_steps") (vision_results.py:31) thay method that, agent_step xuat hien cho session agent_loop; planner bi chan boi kiem exploration_engine != "agent_loop" nen khong co field. Repo tra ORM trong session request dang mo, chi doc cot.
- Test: test_vision_agent_loop.py:822,838-851 dung repo SQL that qua VisionResults, kiem thu tu [1,2,3,4] va scope other_project/other_tenant rong; khong con stub.
- CODEX_BRIDGE_ENABLED: loi collection la moi truong co san: .env:115 cua user dat CODEX_BRIDGE_ENABLED=true va config.py:182 yeu cau tenant local tuong minh; cac phase 1-3 deu chay voi CODEX_BRIDGE_ENABLED=false. Khong do ban sua.

EVIDENCE:
- uv run pytest (khong env): collection error o tests/test_vision_results.py (ValidationError config) - tai hien moi truong.
- CODEX_BRIDGE_ENABLED=false uv run pytest tests/test_vision_agent_loop.py tests/test_vision_results.py tests/test_vision_live_persistence.py -q -> 96 passed, 2 warnings in 253.23s
- uv run ruff check . -> All checks passed!
- git status --short -- benchmark -> rong

OPTIONAL: repo tra ORM con UoW tra detached (khac kieu noi bo tang repo, chap nhan duoc).
