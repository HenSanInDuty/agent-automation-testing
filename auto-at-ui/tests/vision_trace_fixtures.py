"""Synthetic trace data and isolated PostgreSQL databases; never use application settings."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

import pytest
from auto_at.contracts.vision import (
    VisualLocatorHandoff,
    VisualOperation,
    VisualOperationFrame,
)
from domain.entities import VisualOperationFrameRecord
from domain.vision import VisualSessionScope
from infrastructure.persistence.models import (
    Base,
    ProjectModel,
    VisualExplorationSessionModel,
)
from infrastructure.persistence.vision_unit_of_work import SqlAlchemyVisualTraceUnitOfWork
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

TEST_DATABASE_URL = "postgresql+psycopg://postgres:vision-fixture-only@127.0.0.1:55437/postgres"


@pytest.fixture
def disposable_database():
    admin = create_engine(
        TEST_DATABASE_URL, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 2}
    )
    name = "vision_trace_" + uuid4().hex
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
    except OperationalError:
        admin.dispose()
        pytest.skip("isolated PostgreSQL fixture unavailable on 127.0.0.1:55437")
    engine = create_engine(TEST_DATABASE_URL.rsplit("/", 1)[0] + "/" + name)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


def session_values(scope, **overrides):
    values = dict(
        id=scope.session_id,
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        correlation_id=uuid4(),
        target_url="https://fixture.test/",
        intent_hash="a" * 64,
        encrypted_task_intent="fixture-ciphertext",
        intent_retention_until=datetime.now(UTC),
        state="running",
        policy_version="fixture",
        provider="fixture",
        model="fixture",
        prompt_version="fixture",
        max_steps=3,
        max_hops=3,
        max_states=5,
        max_screenshot_bytes=5000,
        max_session_seconds=60,
        max_cost_usd="0",
        max_requests_per_minute=1,
        idempotency_key=uuid4().hex,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    return values | overrides


class MemoryFrameStore:
    def __init__(self):
        self.frames = {}

    def write_operation_frame(self, record, content):
        existing = self.frames.setdefault(record.storage_key, content)
        if existing != content:
            raise ValueError("immutable storage key checksum conflict")

    def read_operation_frame(self, record):
        return self.frames[record.storage_key]

    def delete_operation_frame(self, record):
        self.frames.pop(record.storage_key, None)


@pytest.fixture
def trace_database(disposable_database):
    Base.metadata.create_all(disposable_database)
    factory = sessionmaker(disposable_database, expire_on_commit=False)
    scope = VisualSessionScope("tenant-a", uuid4(), uuid4())
    with factory.begin() as session:
        session.add(
            ProjectModel(
                id=scope.project_id,
                tenant_id=scope.tenant_id,
                name="Fixture",
                default_target="web_ui",
            )
        )
        session.flush()
        session.add(VisualExplorationSessionModel(**session_values(scope, trace_version="v4")))
    store = MemoryFrameStore()
    uow = SqlAlchemyVisualTraceUnitOfWork(factory, store)
    lease = uow.claim(scope, uuid4(), lease_seconds=300)
    assert lease is not None
    return factory, scope, uow, lease, store


def operation(scope, **overrides):
    return VisualOperation.model_validate(
        dict(
            id=uuid4(),
            tenant_id=scope.tenant_id,
            project_id=scope.project_id,
            session_id=scope.session_id,
            sequence=1,
            purpose="setup",
            action_kind="navigate",
            started_at=datetime.now(UTC) - timedelta(seconds=1),
            status="prepared",
        )
        | overrides
    )


def evolve(value, **changes):
    return type(value).model_validate(value.model_dump() | changes)


def frame(operation, role, content=b"synthetic-frame"):
    metadata = VisualOperationFrame(
        id=uuid4(),
        tenant_id=operation.tenant_id,
        project_id=operation.project_id,
        session_id=operation.session_id,
        operation_id=operation.id,
        role=role,
        checksum=sha256(content).hexdigest(),
        byte_count=len(content),
        content_type="image/png",
        captured_at=datetime.now(UTC),
    )
    tenant = sha256(operation.tenant_id.encode()).hexdigest()
    return VisualOperationFrameRecord(
        metadata,
        (
            f"vision-operations/{tenant}/{operation.project_id}/{operation.session_id}/"
            f"{operation.id}/{role}"
        ),
    )


def complete_operation(uow, lease, item):
    uow.commit_prepared(lease, item)
    before = frame(item, "before")
    item = evolve(item, actual_before_frame_id=before.metadata.id)
    uow.commit_captured(lease, before, b"synthetic-frame", item)
    item = evolve(item, status="executing")
    uow.commit_operation(lease, item)
    after = frame(item, "after")
    item = evolve(
        item,
        actual_after_frame_id=after.metadata.id,
        status="completed",
        outcome_code="observed",
        ended_at=datetime.now(UTC),
    )
    uow.commit_captured(lease, after, b"synthetic-frame", item)
    return item


def handoff(scope, **changes):
    values = (
        dict(
            id=uuid4(),
            tenant_id=scope.tenant_id,
            project_id=scope.project_id,
            session_id=scope.session_id,
            version=1,
            branches=(),
            unresolved_count=0,
            created_at=datetime.now(UTC),
            content_hash="0" * 64,
        )
        | changes
    )
    # Validation still parses nested branches before computing the canonical hash.
    import json

    from pydantic_core import to_jsonable_python

    payload = to_jsonable_python(values)
    payload.setdefault("schema_version", "v1")
    payload.pop("content_hash")
    values["content_hash"] = sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    return VisualLocatorHandoff.model_validate(values)
