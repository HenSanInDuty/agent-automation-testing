"""Deterministic exploration conclusions; never a functional test verdict."""

from collections import Counter


def exploration_conclusion(*, state, pages, operations, candidates_not_attempted, legacy=False):
    statuses = Counter(operation.status for operation in operations)
    completed_ids = {
        operation.id for operation in operations
        if operation.status == "completed" and operation.purpose == "explore"
        and operation.action_kind in {"click", "type"}
    }
    controls = {}
    kinds = {}
    for page in pages:
        for control in page.controls:
            # A descriptor can appear on multiple URLs and in many snapshots.
            key = (page.url_fingerprint, control.key)
            completed = control.status == "completed" and control.operation_id in completed_ids
            controls[key] = controls.get(key, False) or completed
            kinds[key] = getattr(control, "button_kind", None)
    observed = len(controls) if pages and not legacy else None
    completed = sum(controls.values()) if observed is not None else None
    remaining = observed - completed if observed is not None else None
    limited = any(page.truncated or page.skipped_count for page in pages)
    pending = sum(count for status, count in statuses.items()
                  if status not in {"completed", "failed", "rejected", "unknown"})
    covered = bool(
        state == "completed" and observed and remaining == 0 and not limited
        and not candidates_not_attempted and not pending
        and not any(statuses[name] for name in ("failed", "rejected", "unknown"))
    )
    scopes = {page.interaction_scope for page in pages}
    return dict(
        status=("in_progress" if state in {"queued", "running"} else
                "cancelled" if state == "cancelled" else "completed" if covered else "partial"),
        coverage="observed_controls_completed" if covered else "not_established",
        interaction_scope=(
            (next(iter(scopes)) if len(scopes) == 1 else "all") if pages else "unknown"
        ),
        observed_controls=observed,
        control_kinds=dict(Counter(kind for kind in kinds.values() if kind)),
        completed_controls=completed,
        remaining_controls=remaining,
        inventory_limited=limited,
        operations_completed=statuses["completed"],
        operations_failed=statuses["failed"],
        operations_rejected=statuses["rejected"],
        operations_unknown=statuses["unknown"],
        operations_pending=pending,
        candidates_not_attempted=candidates_not_attempted,
        business_outcome="unverified",
    )
