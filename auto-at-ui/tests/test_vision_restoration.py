"""Never turn missing, legacy, wrong-page or uncertain evidence into permission to close."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from domain.vision_restoration import (
    can_refresh_undispatched_popup_close,
    can_reobserve_undispatched,
)


def prepare_rejection():
    child, parent, frame_id = uuid4(), uuid4(), uuid4()
    operation = SimpleNamespace(action_kind="close_popup", purpose="restore", status="rejected",
        outcome_code="state_changed_during_prepare", before_page_id=child, after_page_id=None,
        actual_before_frame_id=frame_id, actual_after_frame_id=None,
        after_unavailable_reason="action_not_executed")
    return SimpleNamespace(operation=operation, dispatch_started=False, failure_stage="prepare",
        frames=[SimpleNamespace(id=frame_id, role="before")]), child, parent


def test_prepare_and_dispatch_rejections_require_their_distinct_evidence():
    result, child, parent = prepare_rejection()
    assert can_refresh_undispatched_popup_close(result, child, parent)
    result.failure_stage = "before_dispatch"
    assert not can_refresh_undispatched_popup_close(result, child, parent)
    result.operation.outcome_code = "state_mismatch"
    result.operation.actual_after_frame_id = uuid4()
    result.operation.after_page_id = child
    result.frames.append(SimpleNamespace(id=result.operation.actual_after_frame_id, role="after"))
    assert can_refresh_undispatched_popup_close(result, child, parent)


@pytest.mark.parametrize("change", [
    {"status": "unknown"}, {"status": "failed"}, {"action_kind": "click"},
    {"purpose": "explore"}, {"outcome_code": "state_mismatch"},
    {"outcome_code": "capture_failed"}, {"actual_before_frame_id": None},
    {"before_page_id": uuid4()}, {"after_page_id": uuid4()},
    {"actual_after_frame_id": uuid4()}, {"after_unavailable_reason": "capture_failed"},
])
def test_prepare_rejection_does_not_authorize_refresh_without_full_proof(change):
    result, child, parent = prepare_rejection()
    for name, value in change.items():
        setattr(result.operation, name, value)
    assert not can_refresh_undispatched_popup_close(result, child, parent)


@pytest.mark.parametrize("change", [
    {"dispatch_started": None}, {"dispatch_started": True}, {"failure_stage": None},
    {"failure_stage": "before_dispatch"}, {"frames": []},
    {"frames": [SimpleNamespace(id=uuid4(), role="before")]},
])
def test_legacy_or_inconsistent_transport_is_not_positive_no_dispatch_evidence(change):
    result, child, parent = prepare_rejection()
    for name, value in change.items():
        setattr(result, name, value)
    assert not can_refresh_undispatched_popup_close(result, child, parent)


def test_unknown_or_self_parent_is_not_a_known_child():
    result, child, parent = prepare_rejection()
    for child_id, parent_id in [(None, parent), (child, None), (child, child)]:
        assert not can_refresh_undispatched_popup_close(result, child_id, parent_id)


@pytest.mark.parametrize("action,purpose", [
    ("close_popup", "restore"), ("wait", "setup"), ("wait", "restore"),
])
@pytest.mark.parametrize("stage", ["prepare", "before_dispatch"])
@pytest.mark.parametrize("missing", [
    None, "dispatch", "unknown", "stage", "before_frame", "page", "outcome", "after_proof",
])
def test_recovery_proof_matrix(action, purpose, stage, missing):
    result, child, _ = prepare_rejection()
    op = result.operation
    op.action_kind, op.purpose = action, purpose
    if stage == "before_dispatch":
        result.failure_stage = stage
        op.outcome_code = "state_mismatch"
        op.after_page_id = child
        op.actual_after_frame_id = uuid4()
        result.frames.append(SimpleNamespace(id=op.actual_after_frame_id, role="after"))
    if missing == "dispatch":
        result.dispatch_started = True
    elif missing == "unknown":
        op.status = "unknown"
    elif missing == "stage":
        result.failure_stage = None
    elif missing == "before_frame":
        result.frames = [f for f in result.frames if f.role != "before"]
    elif missing == "page":
        op.before_page_id = uuid4()
    elif missing == "outcome":
        op.outcome_code = "capture_failed"
    elif missing == "after_proof":
        if stage == "prepare":
            op.after_unavailable_reason = "capture_failed"
        else:
            result.frames = [f for f in result.frames if f.role != "after"]
    assert can_reobserve_undispatched(result, child, action, purpose) is (missing is None)


def test_no_dispatch_proof_never_authorizes_click_type_or_navigation_retry():
    result, child, _ = prepare_rejection()
    for action in ["click", "type", "navigate", "back"]:
        result.operation.action_kind = action
        assert not can_reobserve_undispatched(result, child, action, "restore")
