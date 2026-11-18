"""Positive no-dispatch evidence required before refreshing a known popup."""

from uuid import UUID

from auto_at.contracts.vision_worker import VisualWorkerOperationResult


def can_refresh_undispatched_popup_close(
    result: VisualWorkerOperationResult, child_page: UUID | None, parent_page: UUID | None,
) -> bool:
    return (parent_page is not None and parent_page != child_page
            and can_reobserve_undispatched(result, child_page, "close_popup", "restore"))


def can_reobserve_undispatched(
    result: VisualWorkerOperationResult, page_id: UUID | None, action: str, purpose: str,
) -> bool:
    """One proof matrix for read-only refresh, restore verification and popup close."""
    operation = result.operation
    if (page_id is None or (action, purpose) not in {
                ("close_popup", "restore"), ("wait", "setup"), ("wait", "restore"),
            } or operation.action_kind != action or operation.purpose != purpose
            or operation.status != "rejected" or result.dispatch_started is not False
            or operation.before_page_id != page_id or not operation.actual_before_frame_id
            or not any(frame.role == "before" and frame.id == operation.actual_before_frame_id
                       for frame in result.frames)):
        return False
    if result.failure_stage == "prepare":
        # The before-frame was persisted but final prepare validation rejected.
        # An absent after-frame alone is never proof of no physical dispatch.
        return (operation.outcome_code == "state_changed_during_prepare"
                and operation.actual_after_frame_id is None
                and operation.after_page_id is None
                and operation.after_unavailable_reason == "action_not_executed")
    return (result.failure_stage == "before_dispatch"
            and operation.outcome_code == "state_mismatch"
            and operation.actual_after_frame_id is not None
            and operation.after_page_id == page_id
            and any(frame.role == "after" and frame.id == operation.actual_after_frame_id
                    for frame in result.frames))
