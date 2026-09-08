from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from auto_at.contracts.vision import VisualLocatorEvidence
from domain.vision import VisualSessionScope
from infrastructure.persistence.models import (
    VisualActionProposalModel,
    VisualExplorationSessionModel,
    VisualExplorationStateModel,
    VisualOperationModel,
)
from infrastructure.persistence.repositories import SqlAlchemyVisualTraceRepository
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from vision_trace_fixtures import complete_operation, evolve, frame, operation

pytest_plugins = ["vision_trace_fixtures"]


def test_short_commits_visible_to_independent_reader_and_finalization_immutable(trace_database):
    factory, scope, uow, lease, _ = trace_database
    item = operation(scope)
    assert uow.commit_prepared(lease, item) == item
    assert uow.commit_prepared(lease, item) == item
    with factory() as reader:
        assert reader.scalar(select(VisualOperationModel)).status == "prepared"
    before = frame(item, "before")
    prepared = evolve(item, actual_before_frame_id=before.metadata.id)
    uow.commit_captured(lease, before, b"synthetic-frame", prepared)
    with factory() as reader:
        snapshot = SqlAlchemyVisualTraceRepository(reader).snapshot(scope)
        assert snapshot["frames"][0].metadata.id == before.metadata.id
        assert snapshot["operations"][0] == prepared
    running = evolve(prepared, status="executing")
    uow.commit_operation(lease, running)
    failed = evolve(
        running,
        status="unknown",
        ended_at=datetime.now(UTC),
        outcome_code="worker_response_lost",
        after_unavailable_reason="worker_lost",
    )
    assert uow.commit_operation(lease, failed) == failed
    assert uow.commit_operation(lease, failed) == failed
    with pytest.raises(ValueError, match="immutable"):
        uow.commit_operation(lease, evolve(failed, outcome_code="different"))
    assert uow.read_snapshot(scope)["operations"] == (failed,)


def test_scope_mismatches_and_duplicate_sequence_rejected(trace_database):
    _, scope, uow, lease, _ = trace_database
    item = operation(scope)
    uow.commit_prepared(lease, item)
    for changes in ({"tenant_id": "tenant-b"}, {"project_id": uuid4()}, {"session_id": uuid4()}):
        with pytest.raises(ValueError, match="scope"):
            uow.commit_prepared(lease, evolve(item, **changes))
    with pytest.raises(ValueError, match="sequence"):
        uow.commit_prepared(lease, operation(scope))
    with pytest.raises(ValueError, match="scope"):
        uow.commit_prepared(lease, operation(scope, sequence=2, state_id=uuid4()))
    for foreign in (
        VisualSessionScope("tenant-b", scope.project_id, scope.session_id),
        VisualSessionScope(scope.tenant_id, uuid4(), scope.session_id),
    ):
        assert not any(uow.read_snapshot(foreign).values())


def test_lease_takeover_fences_old_writer_and_never_reexecutes_unknown(trace_database):
    factory, scope, uow, lease, _ = trace_database
    item = operation(scope)
    uow.commit_prepared(lease, item)
    assert uow.claim(scope, uuid4()) is None
    with factory.begin() as session:
        session.execute(
            update(VisualExplorationSessionModel).values(
                lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
    replacement = uow.claim(scope, uuid4())
    assert replacement.fencing_token == lease.fencing_token + 1
    with pytest.raises(ValueError, match="stale"):
        uow.commit_prepared(lease, operation(scope, sequence=2))
    failed = evolve(
        item,
        status="failed",
        ended_at=datetime.now(UTC),
        outcome_code="capture_failed",
        before_unavailable_reason="worker_lost",
        after_unavailable_reason="worker_lost",
    )
    with pytest.raises(ValueError, match="only finalize unknown"):
        uow.commit_operation(replacement, failed)
    uow.commit_operation(replacement, evolve(failed, status="unknown"))
    assert uow.renew(replacement).fencing_token == replacement.fencing_token


def test_frame_checksums_tombstones_and_actual_operation_identity(trace_database):
    _, scope, uow, lease, _ = trace_database
    item = operation(scope)
    uow.commit_prepared(lease, item)
    before = frame(item, "before")
    prepared = evolve(item, actual_before_frame_id=before.metadata.id)
    with pytest.raises(ValueError, match="checksum"):
        uow.commit_captured(lease, before, b"wrong", prepared)
    uow.commit_captured(lease, before, b"synthetic-frame", prepared)
    assert uow.commit_captured(lease, before, b"synthetic-frame", prepared) == prepared
    other = frame(item, "before", b"different")
    with pytest.raises(ValueError, match="checksum"):
        uow.commit_captured(
            lease, other, b"different", evolve(item, actual_before_frame_id=other.metadata.id)
        )
    assert uow.tombstone_frame(scope, before.metadata.id)
    assert not uow.tombstone_frame(scope, before.metadata.id)
    snapshot = uow.read_snapshot(scope)
    assert snapshot["frames"][0].metadata.deleted_at
    assert snapshot["operations"][0].actual_before_frame_id == before.metadata.id
    with pytest.raises(ValueError, match="deleted"):
        uow.commit_operation(lease, evolve(prepared, status="executing"))


def test_browser_actions_require_their_own_grounded_locator(trace_database):
    factory, scope, uow, lease, _ = trace_database
    state_id, proposal_id = uuid4(), uuid4()
    with factory.begin() as session:
        session.add(
            VisualExplorationStateModel(
                id=state_id,
                tenant_id=scope.tenant_id,
                session_id=scope.session_id,
                hop=0,
                screenshot_checksum="a" * 64,
            )
        )
        session.flush()
        session.add(
            VisualActionProposalModel(
                id=proposal_id,
                tenant_id=scope.tenant_id,
                session_id=scope.session_id,
                originating_state_id=state_id,
                correlation_id=uuid4(),
                sequence=1,
                action={"kind": "click"},
                policy_version="fixture",
                provider="fixture",
                model="fixture",
                prompt_version="fixture",
            )
        )
    item = operation(
        scope, action_kind="click", purpose="explore", state_id=state_id, proposal_id=proposal_id
    )
    uow.commit_prepared(lease, item)
    before = frame(item, "before")
    item = evolve(item, actual_before_frame_id=before.metadata.id)
    uow.commit_captured(lease, before, b"synthetic-frame", item)
    with pytest.raises(ValueError, match="verified locator"):
        uow.commit_operation(lease, evolve(item, status="executing"))
    locator = VisualLocatorEvidence(
        id=uuid4(),
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        session_id=scope.session_id,
        operation_id=item.id,
        state_id=state_id,
        proposal_id=proposal_id,
        originating_frame_id=before.metadata.id,
        descriptor={"strategy": "role", "role": "button", "value": "Explore"},
        bounding_box={"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.1},
        matched_count=1,
        target_match=True,
        actionable=True,
        model_confidence=0.8,
        verified_at=datetime.now(UTC),
        status="verified",
    )
    item = evolve(item, locator_id=locator.id)
    with pytest.raises(ValueError, match="mismatch"):
        uow.commit_captured(
            lease, before, b"synthetic-frame", item, evolve(locator, proposal_id=uuid4())
        )
    uow.commit_captured(lease, before, b"synthetic-frame", item, locator)
    uow.commit_operation(lease, evolve(item, status="executing"))
    assert uow.read_snapshot(scope)["locators"] == (locator,)
    with pytest.raises(IntegrityError):
        uow.commit_prepared(
            lease,
            evolve(
                item,
                id=uuid4(),
                sequence=2,
                status="prepared",
                actual_before_frame_id=None,
                locator_id=None,
            ),
        )


def test_completed_operation_has_distinct_before_and_after_frames(trace_database):
    _, scope, uow, lease, _ = trace_database
    item = complete_operation(uow, lease, operation(scope))
    snapshot = uow.read_snapshot(scope)
    assert {record.metadata.role for record in snapshot["frames"]} == {"before", "after"}
    assert item.actual_before_frame_id != item.actual_after_frame_id


def test_competing_claims_and_prepares_serialize_without_duplicate_sequence(trace_database):
    from concurrent.futures import ThreadPoolExecutor

    factory, scope, uow, _, _ = trace_database
    with factory.begin() as session:
        session.execute(
            update(VisualExplorationSessionModel).values(
                lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(lambda _: uow.claim(scope, uuid4()), range(2)))
    assert sum(lease is not None for lease in claims) == 1
    lease = next(lease for lease in claims if lease)
    item = operation(scope)
    with ThreadPoolExecutor(max_workers=2) as executor:
        prepared = list(executor.map(lambda _: uow.commit_prepared(lease, item), range(2)))
    assert prepared == [item, item]
    assert len(uow.read_snapshot(scope)["operations"]) == 1


def test_checkpoint_requires_complete_branch_and_never_replaces_invariants(trace_database):
    from auto_at.contracts.vision import VisualCheckpoint

    factory, scope, uow, lease, _ = trace_database
    root = complete_operation(uow, lease, operation(scope))
    child = complete_operation(
        uow, lease, operation(scope, sequence=2, parent_operation_id=root.id)
    )
    state_id = uuid4()
    with factory.begin() as session:
        session.add(
            VisualExplorationStateModel(
                id=state_id,
                tenant_id=scope.tenant_id,
                session_id=scope.session_id,
                hop=1,
                screenshot_checksum="a" * 64,
            )
        )
    checkpoint = VisualCheckpoint(
        id=uuid4(),
        state_id=state_id,
        ancestor_operation_ids=(root.id, child.id),
        url_fingerprint="a" * 64,
        semantic_fingerprint="b" * 64,
        scroll_x=0,
        scroll_y=200,
    )
    with pytest.raises(ValueError, match="one branch"):
        uow.commit_checkpoint(lease, evolve(checkpoint, ancestor_operation_ids=(child.id,)))
    uow.commit_checkpoint(lease, checkpoint)
    uow.commit_checkpoint(lease, checkpoint)
    with pytest.raises(ValueError, match="immutable"):
        uow.commit_checkpoint(lease, evolve(checkpoint, scroll_y=0))
    with pytest.raises(ValueError, match="scope"):
        uow.commit_checkpoint(lease, evolve(checkpoint, state_id=uuid4()))


def test_database_constraints_reject_cross_tenant_session_and_duplicate_sequence(trace_database):
    factory, scope, uow, lease, _ = trace_database
    item = operation(scope)
    uow.commit_prepared(lease, item)
    values = dict(
        id=uuid4(),
        project_id=scope.project_id,
        session_id=scope.session_id,
        tenant_id="tenant-b",
        sequence=2,
        attempt=1,
        status="prepared",
        fencing_token=1,
        payload=item.model_dump(mode="json"),
    )
    with pytest.raises(IntegrityError), factory.begin() as session:
        session.add(VisualOperationModel(**values))
        session.flush()
    with pytest.raises(IntegrityError), factory.begin() as session:
        session.add(
            VisualOperationModel(**(values | {"tenant_id": scope.tenant_id, "sequence": 1}))
        )
        session.flush()
