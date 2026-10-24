"""Owned migrated PostgreSQL fixture; no configured application storage or provider."""

import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import config
import pytest
from alembic import command
from alembic.config import Config
from auto_at.contracts.codex_bridge import CodexBridgeEvent
from domain.codex_bridge import input_snapshot
from domain.vision import VisualSessionScope
from infrastructure.persistence.codex_bridge_repository import SqlAlchemyCodexJobGateway
from infrastructure.persistence.models import (
    CodexBridgeJobModel,
    ProjectModel,
    VisualExplorationSessionModel,
)
from infrastructure.persistence.vision_unit_of_work import SqlAlchemyVisualTraceUnitOfWork
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from test_codex_bridge_contracts import request, response
from test_codex_candidate_service import codex_policy
from vision_trace_fixtures import MemoryFrameStore, session_values

pytest_plugins = ["vision_trace_fixtures"]


@pytest.fixture
def codex_database(disposable_database, monkeypatch):
    url = disposable_database.url.render_as_string(hide_password=False)
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(database_url=url))
    before = {
        name: log.disabled
        for name, log in logging.Logger.manager.loggerDict.items()
        if isinstance(log, logging.Logger)
    }
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        for name, log in logging.Logger.manager.loggerDict.items():
            if isinstance(log, logging.Logger):
                log.disabled = before.get(name, False)
    return disposable_database


def seed(engine, *, target="https://fixture.test/", policy=None):
    policy = policy or codex_policy(max_requests_per_minute=10_000)
    factory = sessionmaker(engine, expire_on_commit=False)
    scope = VisualSessionScope("tenant-codex", uuid4(), uuid4())
    with factory.begin() as db:
        db.add(
            ProjectModel(
                id=scope.project_id,
                tenant_id=scope.tenant_id,
                name="Synthetic Codex fixture",
                default_target="web_ui",
            )
        )
        db.flush()
        db.add(
            VisualExplorationSessionModel(
                **session_values(
                    scope,
                    state="queued",
                    trace_version="v4",
                    provider="codex_cli",
                    model="gpt-6-luna",
                    model_input_policy=input_snapshot(policy).model_dump(mode="json"),
                    target_url=target,
                    max_steps=policy.max_steps,
                    max_requests_per_minute=10_000,
                    max_screenshot_bytes=1_000_000,
                    max_session_seconds=60,
                )
            )
        )
    store = MemoryFrameStore()
    return factory, scope, SqlAlchemyVisualTraceUnitOfWork(factory, store), store, policy


def prepared(engine):
    factory, scope, uow, _, _ = seed(engine)
    lease = uow.claim(scope, uuid4())
    row = uow.running(lease, "codex-dom-v2")
    now = datetime.now(UTC)
    req = request(
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        session_id=scope.session_id,
        correlation_id=row.correlation_id,
        fencing_token=lease.fencing_token,
        created_at=now,
        deadline=now + timedelta(seconds=30),
    )
    return factory, scope, uow, lease, req, SqlAlchemyCodexJobGateway(factory, lease)


async def running(gateway, req):
    await gateway.poll(
        req,
        tuple(
            CodexBridgeEvent(
                job_id=req.job_id,
                sequence=index,
                stage=stage,
                recorded_at=datetime.now(UTC),
            )
            for index, stage in enumerate(("claimed", "running"), 1)
        ),
    )


@pytest.mark.asyncio
async def test_scoped_receipts_commit_once_and_terminal_metadata_is_immutable(codex_database):
    factory, scope, _, _, req, gateway = prepared(codex_database)
    await gateway.register(req)
    with pytest.raises(ValueError, match="duplicate"):
        await gateway.register(req)
    await running(gateway, req)
    await running(gateway, req)  # Duplicate stage delivery is idempotent.
    result = response(req, started_at=datetime.now(UTC), completed_at=datetime.now(UTC))
    await gateway.finish(req, result)
    with factory() as db:
        row = db.scalar(select(CodexBridgeJobModel))
        assert row.status == "completed" and row.response_hash
        assert row.tenant_id == scope.tenant_id and row.actual_model == "gpt-6-luna"
    with pytest.raises(ValueError, match="consumed"):
        await gateway.finish(req, result)
    await gateway.cancel(req, "bridge_cancelled")
    with factory() as db:
        assert db.scalar(select(CodexBridgeJobModel)).status == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", ["tenant", "project", "fence", "deadline", "image"])
async def test_registration_rejects_scope_and_frozen_consent(codex_database, condition):
    factory, _, _, _, req, gateway = prepared(codex_database)
    changes = {
        "tenant": {"tenant_id": "foreign"},
        "project": {"project_id": uuid4()},
        "fence": {"fencing_token": 99},
        "deadline": {"deadline": req.deadline + timedelta(hours=1)},
        "image": {
            "consent": req.consent.model_copy(
                update={
                    "raw_screenshot_transfer_accepted": True,
                    "raw_screenshot_transfer_provider": "codex_cli",
                }
            )
        },
    }[condition]
    with pytest.raises(ValueError):
        await gateway.register(req.model_copy(update=changes))
    with factory() as db:
        assert db.scalar(select(CodexBridgeJobModel)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", ["cancelled", "expired", "stale", "no_receipt"])
async def test_late_or_unclaimed_result_cannot_complete(codex_database, condition):
    factory, scope, _, _, req, gateway = prepared(codex_database)
    await gateway.register(req)
    if condition != "no_receipt":
        await running(gateway, req)
    with factory.begin() as db:
        row = db.get(VisualExplorationSessionModel, scope.session_id)
        if condition == "cancelled":
            row.state = "cancelled"
        elif condition == "expired":
            row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        elif condition == "stale":
            row.fencing_token += 1
    with pytest.raises(ValueError):
        await gateway.finish(
            req, response(req, started_at=datetime.now(UTC), completed_at=datetime.now(UTC))
        )
    await gateway.cancel(req, "bridge_cancelled")
    with factory() as db:
        assert db.scalar(select(CodexBridgeJobModel)).status == "cancelled"


@pytest.mark.asyncio
async def test_recovery_interrupts_old_job_and_does_not_reopen_it(codex_database):
    factory, scope, uow, _, req, gateway = prepared(codex_database)
    await gateway.register(req)
    await running(gateway, req)
    with factory.begin() as db:
        db.get(VisualExplorationSessionModel, scope.session_id).lease_expires_at = datetime.now(
            UTC
        ) - timedelta(seconds=1)
    new_lease = uow.claim(scope, uuid4())
    uow.running(new_lease, "codex-dom-v2")
    with factory() as db:
        job = db.scalar(select(CodexBridgeJobModel))
        assert job.status == "cancelled" and job.safe_reason == "bridge_interrupted"
    with pytest.raises(ValueError):
        await running(gateway, req)
