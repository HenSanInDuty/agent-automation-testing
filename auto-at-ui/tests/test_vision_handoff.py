from datetime import UTC, datetime
from uuid import uuid4

import pytest
from application.vision_handoff import build_vision_handoff
from auto_at.contracts.vision import VisualLocatorDescriptor, VisualLocatorEvidence
from domain.vision import VisualSessionScope
from vision_trace_fixtures import evolve, operation


def branch_fixture(*, input_branch=False, names=("Branch A", "Branch B")):
    scope = VisualSessionScope("tenant-a", uuid4(), uuid4())
    root = operation(
        scope,
        status="completed",
        ended_at=datetime.now(UTC),
        actual_before_frame_id=uuid4(),
        actual_after_frame_id=uuid4(),
        outcome_code="observed",
    )
    operations, locators = [root], []
    for index, name in enumerate(names):
        item = operation(
            scope,
            sequence=index + 2,
            purpose="explore",
            action_kind="type" if input_branch else "click",
            parent_operation_id=root.id,
            status="completed",
            ended_at=datetime.now(UTC),
            state_id=uuid4(),
            proposal_id=uuid4(),
            locator_id=uuid4(),
            actual_before_frame_id=uuid4(),
            actual_after_frame_id=uuid4(),
            outcome_code="observed",
        )
        locator = VisualLocatorEvidence(
            id=item.locator_id,
            tenant_id=scope.tenant_id,
            project_id=scope.project_id,
            session_id=scope.session_id,
            operation_id=item.id,
            state_id=item.state_id,
            proposal_id=item.proposal_id,
            originating_frame_id=item.actual_before_frame_id,
            descriptor=VisualLocatorDescriptor(strategy="role", role="button", value=name),
            bounding_box=dict(x=0.1, y=0.1, width=0.2, height=0.1),
            matched_count=1,
            target_match=True,
            actionable=True,
            model_confidence=0.9,
            verified_at=datetime.now(UTC),
            status="verified",
        )
        operations.append(item)
        locators.append(locator)
    snapshot = dict(operations=tuple(operations), locators=tuple(locators))
    return scope, snapshot, build_vision_handoff(scope, snapshot)


def test_siblings_are_distinct_complete_paths_without_restoration():
    scope, snapshot, package = branch_fixture()
    root, left, right = snapshot["operations"]
    restore = evolve(left, id=uuid4(), purpose="restore", sequence=4)
    package = build_vision_handoff(
        scope, snapshot | {"operations": (*snapshot["operations"], restore)}
    )
    assert [[s.operation_id for s in b.steps] for b in package.branches] == [
        [root.id, left.id],
        [root.id, right.id],
    ]
    assert package.compute_hash() == package.content_hash
    assert all(b.status == "ready" for b in package.branches)


def test_typed_branches_keep_unbound_references_and_cannot_be_ready():
    _, _, package = branch_fixture(input_branch=True)
    assert all(
        b.status == "blocked"
        and b.reason_code == "input_binding_required"
        and b.steps[-1].input_reference
        for b in package.branches
    )


def test_unknown_outcome_is_retained_as_a_blocked_branch():
    scope, snapshot, _ = branch_fixture()
    root, left, right = snapshot["operations"]
    left = evolve(left, status="unknown", outcome_code="action_outcome_unknown")
    package = build_vision_handoff(scope, snapshot | {"operations": (root, left, right)})
    assert package.branches[0].reason_code == "action_outcome_unknown"
    assert package.branches[1].status == "ready"


def test_oversized_handoff_refuses_all_paths_instead_of_silent_truncation():
    with pytest.raises(ValueError, match="handoff_branch_limit"):
        branch_fixture(names=tuple(f"Branch {i}" for i in range(51)))
