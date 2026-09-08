"""Persistence boundaries owned by the domain and implemented by infrastructure."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from auto_at.contracts.execution import TestExecutionRequest, TestExecutionResult
from auto_at.contracts.vision import (
    VisualCheckpoint,
    VisualLocatorEvidence,
    VisualLocatorHandoff,
    VisualOperation,
    VisualOperationFrame,
)
from auto_at.contracts.vision_worker import (
    VisualWorkerAck,
    VisualWorkerExecute,
    VisualWorkerIdentity,
    VisualWorkerOpen,
    VisualWorkerOperationResult,
    VisualWorkerPrepare,
)

from domain.activity import ActivityEvent
from domain.entities import (
    ApprovalRecord,
    ArtifactRecord,
    Project,
    ProposalRecord,
    RunReportRecord,
    TestCase,
    VisualOperationFrameRecord,
    VisualReplayFrameRecord,
    VisualTrajectoryEdgeRecord,
)
from domain.runs import AuditEvent, OutboxEvent, TestRun
from domain.vision import VisualSessionLease, VisualSessionScope


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

    def cancel(self, run: TestRun) -> None: ...


class ArtifactRepository(Protocol):
    def list_for_run(self, tenant_id: str, run_id: UUID) -> list[ArtifactRecord]: ...

    def add(self, artifact: ArtifactRecord) -> None: ...

    def list_expired(self, before: datetime, limit: int) -> list[ArtifactRecord]: ...

    def delete_expired(self, tenant_id: str, artifact_id: UUID) -> bool: ...


class VerifiedArtifactStore(Protocol):
    """Durable, tenant-scoped bytes store; provider details stay in infrastructure."""

    def read_verified_bytes(self, artifact: ArtifactRecord, max_bytes: int) -> bytes: ...

    def delete(self, artifact: ArtifactRecord) -> None: ...

    def list_keys(self, tenant_id: str, run_id: UUID) -> list[str]: ...


class VerifiedVisualReplayStore(Protocol):
    """Private storage for checksum-verified Vision replay bytes."""

    def write_replay_frame(self, frame: VisualReplayFrameRecord, content: bytes) -> None: ...

    def read_replay_frame(self, frame: VisualReplayFrameRecord) -> bytes: ...

    def delete_replay_frame(self, frame: VisualReplayFrameRecord) -> None: ...


class VerifiedVisualOperationStore(Protocol):
    """Create-only deterministic keys: identical retries succeed, different bytes fail."""

    def write_operation_frame(self, frame: VisualOperationFrameRecord, content: bytes) -> None: ...

    def read_operation_frame(self, frame: VisualOperationFrameRecord) -> bytes: ...

    def delete_operation_frame(self, frame: VisualOperationFrameRecord) -> None: ...


class VisualTraceUnitOfWork(Protocol):
    """Each call commits and closes its transaction before returning detached values."""

    def claim(
        self, scope: VisualSessionScope, owner: UUID, *, lease_seconds: int = 30
    ) -> VisualSessionLease | None: ...

    def renew(
        self, lease: VisualSessionLease, *, lease_seconds: int = 30
    ) -> VisualSessionLease: ...

    def commit_prepared(
        self, lease: VisualSessionLease, operation: VisualOperation
    ) -> VisualOperation: ...

    def commit_captured(
        self, lease: VisualSessionLease, record: VisualOperationFrameRecord, content: bytes,
        operation: VisualOperation, locator: VisualLocatorEvidence | None = None,
        *, checkpoint: VisualCheckpoint | None = None,
        semantic_change: str = "unavailable", duration_ms: int = 0,
    ) -> VisualOperation: ...

    def commit_operation(
        self, lease: VisualSessionLease, operation: VisualOperation
    ) -> VisualOperation: ...

    def commit_checkpoint(
        self, lease: VisualSessionLease, checkpoint: VisualCheckpoint
    ) -> None: ...

    def commit_handoff(
        self, lease: VisualSessionLease, handoff: VisualLocatorHandoff
    ) -> VisualLocatorHandoff: ...

    def read_snapshot(self, scope: VisualSessionScope) -> dict[str, tuple]: ...

    def get_session(self, tenant_id: str, session_id: UUID) -> object | None: ...

    def context(self, scope: VisualSessionScope) -> tuple: ...

    def running(self, lease: VisualSessionLease, prompt_version: str) -> object: ...

    def finish(
        self, lease: VisualSessionLease, reason: str | None = None, *,
        handoff: VisualLocatorHandoff | None = None, intent: str | None = None,
        handoff_reason: str | None = None,
    ) -> str: ...

    def progress(self, lease: VisualSessionLease, stage: str, key: str, metadata=None) -> None: ...

    def proposals(self, lease: VisualSessionLease, state_id: UUID, candidates: list) -> None: ...

    def finish_edge(self, lease: VisualSessionLease, edge: VisualTrajectoryEdgeRecord) -> None: ...

    def read_frame(self, scope: VisualSessionScope, frame_id: UUID) -> bytes: ...

    def operation_owners(self, scope: VisualSessionScope) -> dict: ...

    def adopt_result(
        self, lease: VisualSessionLease, operation_id: UUID, old_token: int
    ) -> None: ...


class VisualWorkerTransport(Protocol):
    async def open(self, request: VisualWorkerOpen) -> str: ...

    async def prepare(self, request: VisualWorkerPrepare) -> VisualWorkerOperationResult: ...

    async def execute(self, request: VisualWorkerExecute) -> VisualWorkerOperationResult: ...

    async def read(
        self, identity: VisualWorkerIdentity, operation_id: UUID
    ) -> VisualWorkerOperationResult: ...

    async def frame(self, identity: VisualWorkerIdentity, frame: VisualOperationFrame) -> bytes: ...

    async def acknowledge(self, request: VisualWorkerAck) -> VisualWorkerOperationResult: ...

    async def checkpoint(
        self, identity: VisualWorkerIdentity, checkpoint_id: UUID
    ) -> tuple[VisualCheckpoint, bool]: ...

    async def close(self, identity: VisualWorkerIdentity) -> None: ...


class RunnerTransport(Protocol):
    def execute(self, request: TestExecutionRequest) -> TestExecutionResult: ...


class GeneratedSourcePreflight(Protocol):
    """Checks generated source with its target worker before a run is created."""

    def preflight(self, request: TestExecutionRequest) -> None: ...


class ProposalRepository(Protocol):
    def get(self, tenant_id: str, proposal_id: UUID) -> ProposalRecord | None: ...

    def add(self, proposal: ProposalRecord) -> None: ...


class RunReportRepository(Protocol):
    def get_for_run(
        self, tenant_id: str, run_id: UUID, report_version: int = 1
    ) -> RunReportRecord | None: ...

    def add(self, report: RunReportRecord) -> RunReportRecord: ...


class ApprovalRepository(Protocol):
    def get_final(
        self, tenant_id: str, proposal_id: UUID, proposal_version: int
    ) -> ApprovalRecord | None: ...

    def add(self, approval: ApprovalRecord) -> None: ...


class AuditEventRepository(Protocol):
    def append(self, event: AuditEvent) -> None: ...


class ActivityEventRepository(Protocol):
    def append(self, event: ActivityEvent) -> None: ...

    def list(
        self,
        tenant_id: str,
        *,
        run_id: UUID | None = None,
        correlation_id: UUID | None = None,
        after: datetime | None = None,
    ) -> list[ActivityEvent]: ...


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

    async def cancel_run(self, event: OutboxEvent) -> None: ...


class TriageEventHandler(Protocol):
    async def execute(self, event: OutboxEvent) -> object: ...


class ConfigurationRepository(Protocol):
    """Non-secret values editable later through tenant administration."""

    def get(self, tenant_id: str, key: str) -> dict[str, object] | None: ...

    def set(self, tenant_id: str, key: str, value: dict[str, object]) -> None: ...


class VisualExplorationRepository(Protocol):
    """Stores tenant-scoped exploration metadata and immutable candidate actions."""

    def get(self, tenant_id: str, session_id: UUID) -> object | None: ...

    def get_by_key(self, tenant_id: str, key: str) -> object | None: ...

    def list(self, tenant_id: str, project_id: UUID | None = None) -> list[object]: ...

    def add(self, session: object) -> None: ...

    def add_replay_frame(self, frame: VisualReplayFrameRecord) -> VisualReplayFrameRecord: ...

    def get_replay_frame(
        self, tenant_id: str, session_id: UUID, frame_id: UUID
    ) -> VisualReplayFrameRecord | None: ...

    def list_replay_frames(
        self, tenant_id: str, session_id: UUID
    ) -> list[VisualReplayFrameRecord]: ...

    def delete_replay_frame(self, tenant_id: str, session_id: UUID, frame_id: UUID) -> bool: ...

    def delete_replay_frames(self, tenant_id: str, session_id: UUID) -> int: ...

    def add_trajectory_edge(
        self, edge: VisualTrajectoryEdgeRecord
    ) -> VisualTrajectoryEdgeRecord: ...

    def list_trajectory_edges(
        self, tenant_id: str, session_id: UUID
    ) -> list[VisualTrajectoryEdgeRecord]: ...

    def list_trajectory_edges_for_state(
        self, tenant_id: str, session_id: UUID, state_id: UUID
    ) -> list[VisualTrajectoryEdgeRecord]: ...

    def list_states(self, tenant_id: str, session_id: UUID) -> list[object]: ...

    def add_debug_evidence(self, evidence: object) -> object: ...

    def list_debug_evidence_metadata(self, tenant_id: str, session_id: UUID) -> list[object]: ...

    def get_debug_evidence(self, tenant_id: str, evidence_id: UUID) -> object | None: ...

    def list_expired_debug_evidence(self, before: datetime, limit: int) -> list[object]: ...

    def delete_expired_debug_evidence(self, tenant_id: str, evidence_id: UUID) -> bool: ...
