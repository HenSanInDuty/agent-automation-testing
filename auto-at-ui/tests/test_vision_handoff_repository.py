from types import SimpleNamespace
from uuid import uuid4

import config
import pytest
from alembic import command
from alembic.config import Config
from auto_at.contracts.generation import VisionPlanningSource, vision_generation_key
from auto_at.contracts.vision import VisualHandoffBranch, VisualHandoffStep
from infrastructure.persistence.models import (
    GenerationRequestModel,
    VisualExplorationSessionModel,
    VisualLocatorHandoffModel,
)
from infrastructure.persistence.repositories import SqlAlchemyGenerationRepository
from sqlalchemy import MetaData, Table, inspect, text
from vision_trace_fixtures import (
    complete_operation,
    handoff,
    operation,
    session_values,
)

pytest_plugins = ["vision_trace_fixtures"]


def test_handoff_is_immutable_scoped_and_linked_to_one_generation_request(trace_database):
    factory, scope, uow, lease, _ = trace_database
    item = complete_operation(uow, lease, operation(scope))
    branch = VisualHandoffBranch(
        id=uuid4(), status="ready", steps=(VisualHandoffStep(operation_id=item.id),)
    )
    package = handoff(scope, branches=(branch,))
    assert uow.commit_handoff(lease, package) == package
    assert uow.commit_handoff(lease, package) == package
    with pytest.raises(ValueError, match="immutable"):
        uow.commit_handoff(lease, handoff(scope, branches=(branch,), unresolved_count=1))
    with pytest.raises(ValueError, match="hash"):
        uow.commit_handoff(lease, package.model_copy(update={"content_hash": "a" * 64}))
    request_id = uuid4()
    source = VisionPlanningSource(
        session_id=scope.session_id, handoff_id=package.id, handoff_hash=package.content_hash
    )
    values = dict(
        id=request_id,
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        correlation_id=uuid4(),
        target_url="https://fixture.test/",
        redacted_request="Explore",
        request_hash="a" * 64,
        state="queued",
        vision_handoff_id=package.id,
        idempotency_key=vision_generation_key(source, "Explore"),
    )
    with factory.begin() as session, pytest.raises(ValueError, match="idempotency"):
        SqlAlchemyGenerationRepository(session).add_request(
            GenerationRequestModel(**(values | {"idempotency_key": "intent-only"}))
        )
    with factory.begin() as session:
        SqlAlchemyGenerationRepository(session).add_request(GenerationRequestModel(**values))
    with factory() as reader:
        stored = reader.get(VisualLocatorHandoffModel, package.id)
        assert stored.generation_request_id == request_id
        assert stored.payload == package.model_dump(mode="json")
    with factory.begin() as session, pytest.raises(ValueError, match="already linked"):
        SqlAlchemyGenerationRepository(session).add_request(
            GenerationRequestModel(
                **(values | {"id": uuid4()}),
            )
        )
    for changes in ({"tenant_id": "tenant-b"}, {"project_id": uuid4()}):
        with factory.begin() as session, pytest.raises(ValueError, match="scope"):
            SqlAlchemyGenerationRepository(session).add_request(
                GenerationRequestModel(
                    **(values | changes | {"id": uuid4()}),
                )
            )


def test_handoff_rejects_sibling_concatenation_and_incomplete_paths(trace_database):
    _, scope, uow, lease, _ = trace_database
    root = complete_operation(uow, lease, operation(scope))
    left = complete_operation(uow, lease, operation(scope, sequence=2, parent_operation_id=root.id))
    right = complete_operation(
        uow, lease, operation(scope, sequence=3, parent_operation_id=root.id)
    )

    def branch(*items):
        return VisualHandoffBranch(
            id=uuid4(),
            status="ready",
            steps=tuple(VisualHandoffStep(operation_id=item.id) for item in items),
        )

    for path in (branch(root, left, right), branch(left)):
        with pytest.raises(ValueError, match="complete branch"):
            uow.commit_handoff(lease, handoff(scope, branches=(path,)))
    package = handoff(scope, branches=(branch(root, left), branch(root, right)))
    assert uow.commit_handoff(lease, package) == package


def test_handoff_rejects_unexecuted_operations(trace_database):
    _, scope, uow, lease, _ = trace_database
    item = operation(scope)
    uow.commit_prepared(lease, item)
    branch = VisualHandoffBranch(
        id=uuid4(), status="ready", steps=(VisualHandoffStep(operation_id=item.id),)
    )
    with pytest.raises(ValueError, match="completed operations"):
        uow.commit_handoff(lease, handoff(scope, branches=(branch,)))


def test_submit_uses_scoped_hash_and_original_target_and_is_idempotent(trace_database):
    from application.generation import SubmitGeneration
    from infrastructure.persistence.models import ProjectExecutionPolicyModel
    from infrastructure.persistence.repositories import (
        SqlAlchemyAuditEventRepository,
        SqlAlchemyOutboxEventRepository,
    )

    factory, scope, uow, lease, _ = trace_database
    item = complete_operation(uow, lease, operation(scope))
    package = handoff(
        scope,
        branches=(
            VisualHandoffBranch(
                id=uuid4(),
                status="ready",
                steps=(VisualHandoffStep(operation_id=item.id),),
            ),
        ),
    )
    uow.commit_handoff(lease, package)
    with factory.begin() as session:
        session.add(
            ProjectExecutionPolicyModel(
                tenant_id=scope.tenant_id,
                project_id=scope.project_id,
                allowed_origins=["https://fixture.test"],
            )
        )
    values = dict(
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        correlation_id=uuid4(),
        target_url="https://fixture.test/",
        natural_language_request="Explore",
        idempotency_key="ignored-client-key",
        vision_handoff_id=package.id,
    )
    with factory.begin() as session:
        use_case = SubmitGeneration(
            SqlAlchemyGenerationRepository(session),
            SqlAlchemyAuditEventRepository(session),
            SqlAlchemyOutboxEventRepository(session),
        )
        with pytest.raises(ValueError, match="target mismatch"):
            use_case.execute(**(values | {"target_url": "https://fixture.test/other"}))
        with pytest.raises(ValueError, match="handoff unavailable"):
            use_case.execute(**(values | {"vision_handoff_id": uuid4()}))
        first = use_case.execute(**values)
        assert use_case.execute(**(values | {"idempotency_key": "different"})).id == first.id
        assert len(SqlAlchemyOutboxEventRepository(session).list_unpublished(100)) == 1


def test_additive_migration_preserves_legacy_rows_and_defaults(disposable_database, monkeypatch):
    # Alembic runs exclusively against a UUID-named test database, not configured app storage.
    url = disposable_database.url.render_as_string(hide_password=False)
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(database_url=url))
    alembic = Config("alembic.ini")
    command.upgrade(alembic, "f8a9b0c1d2e3")
    from domain.vision import VisualSessionScope

    scope = VisualSessionScope("legacy-tenant", uuid4(), uuid4())
    metadata = MetaData()
    projects = Table("projects", metadata, autoload_with=disposable_database)
    sessions = Table("visual_exploration_sessions", metadata, autoload_with=disposable_database)
    requests = Table("generation_requests", metadata, autoload_with=disposable_database)
    request_id = uuid4()
    with disposable_database.begin() as connection:
        connection.execute(
            projects.insert().values(
                id=scope.project_id,
                tenant_id=scope.tenant_id,
                name="Legacy",
                default_target="web_ui",
            )
        )
        connection.execute(sessions.insert().values(**session_values(scope)))
        connection.execute(
            requests.insert().values(
                id=request_id,
                tenant_id=scope.tenant_id,
                project_id=scope.project_id,
                correlation_id=uuid4(),
                target_url="https://fixture.test/",
                redacted_request="Explore",
                request_hash="a" * 64,
                state="completed",
                idempotency_key=uuid4().hex,
            )
        )
    command.upgrade(alembic, "head")
    from sqlalchemy.orm import Session

    with Session(disposable_database) as reader:
        legacy = reader.get(VisualExplorationSessionModel, scope.session_id)
        assert legacy.encrypted_task_intent == "fixture-ciphertext"
        assert legacy.trace_version == "legacy"
        assert legacy.fencing_token == 0 and legacy.next_operation_sequence == 1
        assert legacy.lease_owner is None and legacy.lease_expires_at is None
        assert reader.get(GenerationRequestModel, request_id).vision_handoff_id is None
        assert reader.scalar(text("SELECT version_num FROM alembic_version")) == "f9a0b1c2d3e4"
    assert {
        "visual_operations",
        "visual_operation_frames",
        "visual_locator_evidence",
        "visual_locator_handoffs",
    } <= set(inspect(disposable_database).get_table_names())
