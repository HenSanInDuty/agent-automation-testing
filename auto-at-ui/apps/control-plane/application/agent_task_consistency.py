"""ADR-047 phase B2: how consistently sessions of the same task reported the same assessment.

Read-only: no write, no model call, no new run, no draft. Agreement is the share of assessed
sessions that repeat the most common status (same definition as `benchmark/task_ui/stability.py`
`_task_stats`; rewritten here because the control plane never imports `benchmark/`). It lowers
random noise only: sessions can agree on a wrong status, so it is never evidence that a status is
correct.
"""

from collections import Counter
from uuid import UUID

from domain.authorization import Permission, Principal
from domain.vision_task_assessment import ASSESSMENT_STATUSES

from application.vision_replay import VisionReplay

SCHEMA_VERSION = "v1"
# Below this many assessed sessions a high agreement rate says little; the report says so.
SMALL_SAMPLE_SESSIONS = 3
NOTICE = (
    "Agreement counts how often sessions repeated the same status. It reduces random noise only; "
    "sessions can agree on a wrong status, so this is not proof the status is correct."
)


def summarise_group(source_status, statuses, threshold: float) -> dict:
    """`statuses`: assessment status of every completed, assessed session of the group.

    `source_status`: the requested session's own status, or None when it is not in `statuses`.
    """
    counts = Counter(statuses)
    assessed = sum(counts.values())
    # Highest count wins; a tie goes to the alphabetically first status (stability.py:138).
    modal = min(counts.items(), key=lambda pair: (-pair[1], pair[0]))[0] if counts else None
    agreement = round(counts[modal] / assessed, 4) if modal else None
    reasons = []
    if modal != "achieved":
        reasons.append("modal_not_achieved")
    if source_status is None or source_status != modal:
        reasons.append("source_not_modal")
    if agreement is None or agreement < threshold:
        reasons.append("assessment_inconsistent")
    return {
        "schema_version": SCHEMA_VERSION,
        "assessed_sessions": assessed,
        "status_counts": {status: counts[status] for status in sorted(ASSESSMENT_STATUSES)},
        "modal_status": modal,
        "modal_count": counts[modal] if modal else 0,
        "agreement_rate": agreement,
        "source_status": source_status,
        "source_is_modal": source_status is not None and source_status == modal,
        "threshold": threshold,
        "small_sample": assessed < SMALL_SAMPLE_SESSIONS,
        "eligible": not reasons,
        "reasons": reasons,
        "advisory": True,
        "notice": NOTICE,
    }


def read_consistency(
    sessions, *, tenant_id: str, principal: Principal, session_id: UUID, threshold: float
) -> dict:
    """`sessions`: `SqlAlchemyVisionRepository`.

    Raises `VisionReplayNotFoundError` for a session that is missing or not readable by the
    caller (the two are not told apart).
    """
    # ponytail: reuse the replay READ check instead of a second copy of the not-found rule.
    source = VisionReplay(sessions, None, None)._session(
        tenant_id, principal, session_id, Permission.READ
    )
    group = sessions.list_same_task(tenant_id, source.project_id, source.target_url,
                                    source.intent_hash)
    assessed = {
        item.id: item.task_assessment["status"]
        for item in group
        if item.state == "completed" and isinstance(item.task_assessment, dict)
        and item.task_assessment.get("status") in ASSESSMENT_STATUSES
    }
    report = summarise_group(assessed.get(source.id), list(assessed.values()), threshold)
    return {"session_id": str(session_id), "group_sessions": len(group)} | report
