from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest
from auto_at.contracts.execution import RunStatus
from auto_at.contracts.execution import TestExecutionResult as ExecutionResult
from domain.runs import AuditEvent, RunLifecycleStatus, RunStateError
from domain.runs import TestRun as DomainTestRun


def make_run() -> DomainTestRun:
    return DomainTestRun.create(
        tenant_id="tenant-a",
        project_id=uuid4(),
        test_case_id="checkout-happy-path",
        revision="a" * 40,
        correlation_id=uuid4(),
    )


def test_new_run_is_queued_with_an_immutable_revision() -> None:
    run = make_run()

    assert run.status is RunLifecycleStatus.QUEUED
    with pytest.raises(RunStateError, match="immutable"):
        run.change_revision("b" * 40)


def test_matching_runner_result_sets_the_only_terminal_verdict() -> None:
    run = make_run()
    result = ExecutionResult(
        run_id=run.id,
        correlation_id=run.correlation_id,
        status=RunStatus.PASSED,
        started_at="2026-07-20T08:00:00Z",
        completed_at="2026-07-20T08:01:00Z",
        summary="Passed.",
    )

    run.record_runner_result(result)

    assert run.status is RunLifecycleStatus.PASSED
    assert run.result is result
    with pytest.raises(RunStateError, match="terminal"):
        run.record_runner_result(result)


def test_runner_result_for_another_run_is_rejected() -> None:
    run = make_run()
    result = ExecutionResult(
        run_id=uuid4(),
        correlation_id=run.correlation_id,
        status=RunStatus.FAILED,
        started_at="2026-07-20T08:00:00Z",
        completed_at="2026-07-20T08:01:00Z",
        summary="Failed.",
    )

    with pytest.raises(RunStateError, match="run_id"):
        run.record_runner_result(result)


def test_audit_event_is_append_only() -> None:
    event = AuditEvent(
        id=uuid4(),
        tenant_id="tenant-a",
        actor="reviewer",
        action="run.created",
        entity_type="test_run",
        entity_id=uuid4(),
        correlation_id=uuid4(),
    )

    with pytest.raises(FrozenInstanceError):
        event.action = "run.deleted"
