"""ADR-047 phase B1: read one agent-loop session in its own scope and build its task trace.

Read-only: no table, no write, no model call. Permission checks belong to the caller (the draft
route, phase 14); this function only guarantees that data of another tenant or project is never
read.
"""

from auto_at.contracts.agent_task_trace import AgentTaskTrace
from domain.agent_task_trace import build_agent_task_trace
from domain.vision import VisualSessionScope


class AgentTaskTraceNotFound(LookupError):
    """Missing, or outside the given tenant/project: the two are not told apart."""


def read_agent_task_trace(sessions, trace, scope: VisualSessionScope) -> AgentTaskTrace:
    """`sessions`: `SqlAlchemyVisionRepository`; `trace`: `SqlAlchemyVisualTraceRepository`.

    Raises `AgentTaskTraceNotFound` for a session that is not in `scope`, and
    `domain.agent_task_trace.AgentTaskTraceRefused` when the evidence cannot make a trace.
    """
    record = sessions.get(scope.tenant_id, scope.session_id)
    if record is None or record.project_id != scope.project_id:
        raise AgentTaskTraceNotFound
    snapshot = trace.snapshot(scope)
    return build_agent_task_trace(
        record,
        trace.agent_steps(scope),
        snapshot["operations"],
        snapshot["locators"],
        snapshot["frames"],
    )
