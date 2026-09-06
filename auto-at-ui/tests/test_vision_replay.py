"""Authorization and byte-first deletion rules for Vision replay evidence."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from application.vision_replay import (
    VisionReplay,
    VisionReplayDeletionError,
    VisionReplayNotFoundError,
)
from domain.authorization import Principal, Role
from domain.entities import VisualReplayFrameRecord


class Repository:
    def __init__(self, session, frames):
        self.session, self.frames = session, list(frames)
        self.operations: list[str] = []

    def get(self, tenant_id, session_id):
        if tenant_id == self.session.tenant_id and session_id == self.session.id:
            return self.session
        return None

    def list_replay_frames(self, tenant_id, session_id):
        return self.frames if self.get(tenant_id, session_id) else []

    def get_replay_frame(self, tenant_id, session_id, frame_id):
        return next(
            (
                frame
                for frame in self.list_replay_frames(tenant_id, session_id)
                if frame.id == frame_id
            ),
            None,
        )

    def list_actions(self, tenant_id, session_id):
        return []

    def delete_replay_frame(self, tenant_id, session_id, frame_id):
        frame = self.get_replay_frame(tenant_id, session_id, frame_id)
        if frame is None:
            return False
        self.operations.append("metadata")
        self.frames.remove(frame)
        return True


class Store:
    def __init__(self, content=b"\x89PNG\r\n\x1a\nreplay", *, fail_delete=False):
        self.content, self.fail_delete = content, fail_delete
        self.operations: list[str] = []

    def read_replay_frame(self, frame):
        self.operations.append("read")
        return self.content

    def delete_replay_frame(self, frame):
        self.operations.append("bytes")
        if self.fail_delete:
            raise RuntimeError("storage unavailable")


class Audits:
    def __init__(self):
        self.items = []

    def append(self, event):
        self.items.append(event)


def replay_fixture():
    tenant_id, project_id, session_id, frame_id = "tenant-a", uuid4(), uuid4(), uuid4()
    session = SimpleNamespace(
        id=session_id, tenant_id=tenant_id, project_id=project_id, correlation_id=uuid4()
    )
    frame = VisualReplayFrameRecord(
        id=frame_id,
        tenant_id=tenant_id,
        session_id=session_id,
        state_id=uuid4(),
        sequence=1,
        storage_key=f"tenants/{tenant_id}/vision-explorations/{session_id}/states/state.png",
        checksum="a" * 64,
        size=14,
        content_type="image/png",
        captured_at=datetime.now(UTC),
    )
    return tenant_id, project_id, session, frame


@pytest.mark.parametrize(
    "role", [Role.VIEWER, Role.CONTRIBUTOR, Role.REVIEWER, Role.PROJECT_ADMIN, Role.TENANT_ADMIN]
)
def test_all_human_reader_roles_can_list_and_read_a_project_replay(role) -> None:
    tenant_id, project_id, session, frame = replay_fixture()
    repository, store, audits = Repository(session, [frame]), Store(), Audits()
    principal = Principal("reader", {}, {(tenant_id, project_id): frozenset({role})})
    replay = VisionReplay(repository, store, audits)

    assert replay.list(tenant_id=tenant_id, principal=principal, session_id=session.id)[0] == [
        frame
    ]
    assert (
        replay.read(
            tenant_id=tenant_id, principal=principal, session_id=session.id, frame_id=frame.id
        )
        == store.content
    )
    assert [event.action for event in audits.items] == ["vision.replay_frame_read"]


def test_service_and_cross_tenant_callers_cannot_enumerate_replay_evidence() -> None:
    tenant_id, project_id, session, frame = replay_fixture()
    replay = VisionReplay(Repository(session, [frame]), Store(), Audits())
    service = Principal("worker", {tenant_id: frozenset({Role.SERVICE})}, {}, is_service=True)
    other_tenant_admin = Principal("other", {"tenant-b": frozenset({Role.TENANT_ADMIN})}, {})

    # Generic service READ never grants access to human-facing replay evidence.
    with pytest.raises(VisionReplayNotFoundError):
        replay.list(tenant_id=tenant_id, principal=service, session_id=session.id)
    with pytest.raises(VisionReplayNotFoundError):
        replay.read(
            tenant_id="tenant-b",
            principal=other_tenant_admin,
            session_id=session.id,
            frame_id=frame.id,
        )


def test_only_non_service_tenant_admin_can_delete_bytes_before_metadata_and_retry_safely() -> None:
    tenant_id, project_id, session, frame = replay_fixture()
    repository, store, audits = Repository(session, [frame]), Store(), Audits()
    replay = VisionReplay(repository, store, audits)
    project_admin = Principal(
        "project-admin", {}, {(tenant_id, project_id): frozenset({Role.PROJECT_ADMIN})}
    )
    tenant_admin = Principal("tenant-admin", {tenant_id: frozenset({Role.TENANT_ADMIN})}, {})
    service_admin = Principal(
        "service", {tenant_id: frozenset({Role.TENANT_ADMIN})}, {}, is_service=True
    )

    with pytest.raises(VisionReplayNotFoundError):
        replay.delete_one(
            tenant_id=tenant_id, principal=project_admin, session_id=session.id, frame_id=frame.id
        )
    with pytest.raises(VisionReplayNotFoundError):
        replay.delete_one(
            tenant_id=tenant_id, principal=service_admin, session_id=session.id, frame_id=frame.id
        )
    assert replay.delete_one(
        tenant_id=tenant_id, principal=tenant_admin, session_id=session.id, frame_id=frame.id
    )
    assert store.operations == ["bytes"]
    assert repository.operations == ["metadata"]
    assert not replay.delete_one(
        tenant_id=tenant_id, principal=tenant_admin, session_id=session.id, frame_id=frame.id
    )
    assert [event.action for event in audits.items] == [
        "vision.replay_frame_delete_requested",
        "vision.replay_frame_delete_completed",
    ]


def test_failed_byte_delete_preserves_metadata_for_a_safe_retry() -> None:
    tenant_id, _, session, frame = replay_fixture()
    repository, store, audits = Repository(session, [frame]), Store(fail_delete=True), Audits()
    tenant_admin = Principal("tenant-admin", {tenant_id: frozenset({Role.TENANT_ADMIN})}, {})

    with pytest.raises(VisionReplayDeletionError):
        VisionReplay(repository, store, audits).delete_one(
            tenant_id=tenant_id, principal=tenant_admin, session_id=session.id, frame_id=frame.id
        )
    assert repository.frames == [frame]
    assert repository.operations == []
    assert [event.action for event in audits.items] == [
        "vision.replay_frame_delete_requested",
        "vision.replay_frame_delete_failed",
    ]
