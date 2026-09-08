from datetime import UTC, datetime
from uuid import uuid4

import pytest
from domain.entities import VisualTrajectoryEdgeRecord
from infrastructure.persistence.repositories import SqlAlchemyVisionRepository


class FakeSession:
    def __init__(self) -> None:
        self.existing = None
        self.added = []

    def scalar(self, _statement):
        return self.existing

    def add(self, model):
        self.added.append(model)

    def flush(self):
        return None


def edge(**overrides) -> VisualTrajectoryEdgeRecord:
    values = {
        "id": uuid4(), "tenant_id": "tenant-a", "session_id": uuid4(),
        "parent_state_id": uuid4(), "proposal_id": uuid4(), "attempt": 1,
        "action": {"kind": "click", "x": 0.5, "y": 0.5}, "confidence": 0.8,
        "status": "observed", "outcome_code": None, "child_state_id": uuid4(),
        "observed_at": datetime.now(UTC), "duration_ms": 10, "url_fingerprint": None,
        "url_change": "unchanged", "child_screenshot_checksum": "a" * 64,
        "created_at": datetime.now(UTC),
    }
    values.update(overrides)
    return VisualTrajectoryEdgeRecord(**values)


def test_trajectory_edge_insert_is_idempotent_and_allows_missing_child() -> None:
    session = FakeSession()
    repository = SqlAlchemyVisionRepository(session)
    record = edge(child_state_id=None, child_screenshot_checksum=None, status="failed")

    stored = repository.add_trajectory_edge(record)
    assert stored.child_state_id is None
    assert len(session.added) == 1

    session.existing = session.added[0]
    duplicate = repository.add_trajectory_edge(record)
    assert duplicate.id == record.id
    assert len(session.added) == 1


def test_trajectory_edge_rejects_divergent_duplicate() -> None:
    session = FakeSession()
    repository = SqlAlchemyVisionRepository(session)
    record = edge()
    repository.add_trajectory_edge(record)
    session.existing = session.added[0]

    with pytest.raises(ValueError, match="immutable proposal attempt"):
        repository.add_trajectory_edge(edge(**{**record.__dict__, "confidence": 0.2}))


def test_trajectory_edge_allows_one_idempotent_proposed_to_observed_finalization() -> None:
    session = FakeSession()
    repository = SqlAlchemyVisionRepository(session)
    proposed = edge(
        status="proposed", child_state_id=None, observed_at=None, duration_ms=0,
        url_fingerprint=None, url_change="unavailable", child_screenshot_checksum=None,
    )
    repository.add_trajectory_edge(proposed)
    session.existing = session.added[0]
    finalized = edge(**{**proposed.__dict__, "status": "observed", "child_state_id": uuid4(),
                      "observed_at": datetime.now(UTC), "duration_ms": 12,
                      "url_fingerprint": "b" * 64, "url_change": "changed",
                      "child_screenshot_checksum": "c" * 64})

    assert repository.add_trajectory_edge(finalized).status == "observed"
    assert session.existing.child_state_id == finalized.child_state_id
    assert repository.add_trajectory_edge(finalized).status == "observed"
