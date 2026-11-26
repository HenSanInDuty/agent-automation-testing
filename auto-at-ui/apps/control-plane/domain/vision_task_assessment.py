"""ADR-046: how an agent-loop session reports what happened to its task.

The assessment is advisory. It records what the agent says it observed, next to counts the
controller measured itself; it is never a test verdict (`business_outcome` stays `unverified`).
Every natural end of the loop produces one, so a finished session is `completed` with a status
instead of `unavailable` with a reason.
"""

from collections import Counter
from collections.abc import Iterable

ASSESSMENT_SCHEMA_VERSION = "v1"
# achieved / not_achieved / blocked come from the agent; inconclusive only from the controller.
ASSESSMENT_STATUSES = frozenset({"achieved", "not_achieved", "blocked", "inconclusive"})
STOP_SUMMARIES = {
    "complete": "The agent reported the task complete without a detailed assessment.",
    "no_safe_action": "The agent found no allowed action that could advance the task.",
    "unsupported_state": "The agent could not handle the page it reached.",
}


def action_facts(entries: Iterable[dict]) -> dict[str, int]:
    """Controller-measured counts over every action entry of the step log."""
    counts = Counter()
    for entry in entries:
        if entry.get("skipped_reason"):
            counts["blocked_or_skipped"] += 1
        else:
            status = (entry.get("result") or {}).get("status")
            counts[status if status in {"completed", "failed", "rejected"} else "other"] += 1
    return {
        "actions_completed": counts["completed"],
        "actions_failed": counts["failed"] + counts["rejected"],
        "actions_blocked_or_skipped": counts["blocked_or_skipped"],
    }


def _assessment(status, summary, checks, source, stop_reason, facts) -> dict:
    if status not in ASSESSMENT_STATUSES:
        raise ValueError("unknown task assessment status")
    return {
        "schema_version": ASSESSMENT_SCHEMA_VERSION,
        "status": status,
        "summary": summary,
        "checks": checks,
        "source": source,
        "stop_reason": stop_reason,
        "facts": facts,
        "advisory": True,
    }


def from_task_result(result, facts: dict[str, int]) -> dict:
    """The agent's own end-of-task report (`AgentTaskResult`)."""
    checks = [check.model_dump(mode="json") for check in result.checks]
    return _assessment(result.status, result.summary, checks, "agent", "agent_done", facts)


def from_stop(reason: str, facts: dict[str, int]) -> dict:
    """A bare stop: `complete` is taken at its word, the other reasons mean blocked."""
    summary = STOP_SUMMARIES.get(reason, STOP_SUMMARIES["unsupported_state"])
    if reason == "complete":
        return _assessment("achieved", summary, [], "agent", "agent_done", facts)
    return _assessment("blocked", summary, [], "agent", "agent_stopped", facts)


def from_step_limit(facts: dict[str, int]) -> dict:
    """The call budget ran out before the agent reported; nothing is claimed about the task."""
    return _assessment(
        "inconclusive",
        "The model call budget ran out before the agent reported a result.",
        [], "controller", "agent_step_limit", facts,
    )
