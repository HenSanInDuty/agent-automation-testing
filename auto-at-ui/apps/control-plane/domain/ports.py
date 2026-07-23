"""Persistence boundaries owned by the domain and implemented by infrastructure."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from auto_at.contracts.execution import TestExecutionRequest, TestExecutionResult

from domain.entities import ApprovalRecord, ArtifactRecord, Project, ProposalRecord, TestCase
from domain.runs import AuditEvent, OutboxEvent, TestRun


class ProjectRepository(Protocol):
    def get(self, tenant_id: str, project_id: UUID) -> Project | None: ...

    def add(self, project: Project) -> None: ...


class TestCaseRepository(Protocol):
    def get(self, tenant_id: str, test_case_id: str) -> TestCase | None: ...

    def add(self, test_case: TestCase) -> None: ...


class RunRepository(Protocol):
    def get(self, tenant_id: str, run_id: UUID) -> TestRun | None: ...

    def add(self, run: TestRun) -> None: ...

    def save_result(self, run: TestRun, result: TestExecutionResult) -> None: ...


class ArtifactRepository(Protocol):
    def list_for_run(self, tenant_id: str, run_id: UUID) -> list[ArtifactRecord]: ...

    def add(self, artifact: ArtifactRecord) -> None: ...


class RunnerTransport(Protocol):
    def execute(self, request: "TestExecutionRequest") -> TestExecutionResult: ...


class ProposalRepository(Protocol):
    def get(self, tenant_id: str, proposal_id: UUID) -> ProposalRecord | None: ...

    def add(self, proposal: ProposalRecord) -> None: ...


class ApprovalRepository(Protocol):
    def get_final(self, proposal_id: UUID, proposal_version: int) -> ApprovalRecord | None: ...

    def add(self, approval: ApprovalRecord) -> None: ...


class AuditEventRepository(Protocol):
    def append(self, event: AuditEvent) -> None: ...


class OutboxEventRepository(Protocol):
    def get_by_idempotency_key(
        self, tenant_id: str, idempotency_key: str
    ) -> OutboxEvent | None: ...

    def append(self, event: OutboxEvent) -> None: ...

    def list_unpublished(self, limit: int) -> list[OutboxEvent]: ...

    def mark_published(self, event_id: UUID, published_at: datetime) -> None: ...


class WorkflowStarter(Protocol):
    """Starts durable orchestration without exposing a vendor SDK to application code."""

    async def start_run(self, event: OutboxEvent) -> None: ...
