"""Fenced short transactions; never retain an ORM session across browser/model awaits."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from types import SimpleNamespace
from uuid import UUID, uuid4

from auto_at.contracts.vision import (
    VisualCheckpoint,
    VisualLocatorEvidence,
    VisualLocatorHandoff,
    VisualOperation,
)
from domain.activity import ActivityEvent
from domain.entities import VisualOperationFrameRecord
from domain.ports import VerifiedVisualOperationStore
from domain.runs import AuditEvent
from domain.vision import VisualSessionLease, VisualSessionScope
from sqlalchemy import select
from sqlalchemy.orm import Session

from infrastructure.persistence.models import (
    VisualActionProposalModel,
    VisualExplorationStateModel,
    VisualOperationModel,
)
from infrastructure.persistence.repositories import (
    SqlAlchemyActivityEventRepository,
    SqlAlchemyAuditEventRepository,
    SqlAlchemyConfigurationRepository,
    SqlAlchemyGenerationRepository,
    SqlAlchemyOutboxEventRepository,
    SqlAlchemyVisionRepository,
    SqlAlchemyVisualTraceRepository,
)
from infrastructure.persistence.session import transactional_session


class SqlAlchemyVisualTraceUnitOfWork:
    def __init__(
        self,
        factory: Callable[[], Session],
        store: VerifiedVisualOperationStore | None = None,
    ) -> None:
        self._factory = factory
        self._store = store

    @staticmethod
    def _detached(model):
        if model is None:
            return None
        return SimpleNamespace(**{c.key: getattr(model, c.key) for c in model.__table__.columns})

    def get_session(self, tenant_id, session_id):
        with transactional_session(self._factory) as session:
            return self._detached(SqlAlchemyVisionRepository(session).get(tenant_id, session_id))

    def context(self, scope):
        with transactional_session(self._factory) as session:
            record = SqlAlchemyVisionRepository(session).get(scope.tenant_id, scope.session_id)
            if record is None or record.project_id != scope.project_id:
                raise ValueError("visual session scope mismatch")
            config = SqlAlchemyConfigurationRepository(session).get(
                scope.tenant_id,
                "agent.runtime.v1",
            )
            policy = SqlAlchemyGenerationRepository(session).get_policy(
                scope.tenant_id,
                scope.project_id,
            )
            return self._detached(record), config, self._detached(policy)

    def progress(self, lease, stage, key, metadata=None):
        with transactional_session(self._factory) as session:
            self._progress(session, lease, stage, key, metadata)

    @staticmethod
    def _progress(session, lease, stage, key, metadata=None):
        record = SqlAlchemyVisualTraceRepository(session)._fence(lease)
        SqlAlchemyActivityEventRepository(session).append(
            ActivityEvent.create_vision_progress(
                tenant_id=record.tenant_id,
                correlation_id=record.correlation_id,
                visual_exploration_session_id=record.id,
                stage=stage,
                progress_key=key,
                occurred_at=datetime.now(UTC),
                metadata=metadata,
            )
        )

    def running(self, lease, prompt_version):
        with transactional_session(self._factory) as session:
            record = SqlAlchemyVisualTraceRepository(session)._fence(lease)
            if record.state == "queued":
                record.state, record.updated_at = "running", datetime.now(UTC)
                record.prompt_version = prompt_version
                self._progress(session, lease, "started", "started")
            return self._detached(record)

    def finish(self, lease, reason=None, *, handoff=None, intent=None, handoff_reason=None):
        with transactional_session(self._factory) as session:
            record = SqlAlchemyVisualTraceRepository(session)._fence(lease)
            repository = SqlAlchemyVisionRepository(session)
            for edge in repository.list_trajectory_edges(record.tenant_id, record.id):
                if edge.status == "proposed":
                    repository.add_trajectory_edge(
                        replace(
                            edge,
                            status="failed" if reason else "terminal",
                            outcome_code="candidate_rejected" if reason else "state_limit",
                        )
                    )
            if record.state != "cancelled":
                record.state = "unavailable" if reason else "completed"
            record.safe_failure_reason = reason
            if handoff is not None:
                SqlAlchemyVisualTraceRepository(session).add_handoff(lease, handoff)
                accepted = False
                if record.state == "completed" and any(
                    b.status == "ready" for b in handoff.branches
                ):
                    try:
                        with session.begin_nested():
                            from application.generation import SubmitGeneration

                            SubmitGeneration(
                                SqlAlchemyGenerationRepository(session),
                                SqlAlchemyAuditEventRepository(session),
                                SqlAlchemyOutboxEventRepository(session),
                            ).execute(
                                tenant_id=record.tenant_id,
                                project_id=record.project_id,
                                correlation_id=record.correlation_id,
                                target_url=record.target_url,
                                natural_language_request=intent,
                                idempotency_key=f"vision:{handoff.id}",
                                vision_handoff_id=handoff.id,
                            )
                            accepted = True
                    except Exception:
                        # Keep the immutable bundle and trace after a rejected request.
                        accepted = False
                stage = "handoff.ready" if accepted else "handoff.unavailable"
                metadata = (
                    None
                    if accepted
                    else {
                        "reason_code": (
                            "generation_request_unavailable"
                            if any(b.status == "ready" for b in handoff.branches)
                            else "no_eligible_branches"
                        )
                    }
                )
                self._progress(session, lease, stage, stage, metadata)
            elif handoff_reason:
                self._progress(
                    session,
                    lease,
                    "handoff.unavailable",
                    "handoff.unavailable",
                    {"reason_code": handoff_reason},
                )
            self._progress(
                session,
                lease,
                "unavailable" if reason else "completed",
                "unavailable" if reason else "completed",
            )
            SqlAlchemyAuditEventRepository(session).append(
                AuditEvent(
                    id=uuid4(),
                    tenant_id=record.tenant_id,
                    actor="vision-worker",
                    action=f"vision.exploration_{record.state}",
                    entity_type="visual_exploration_session",
                    entity_id=record.id,
                    correlation_id=record.correlation_id,
                )
            )
            return record.state

    def proposals(self, lease, state_id, candidates):
        with transactional_session(self._factory) as session:
            record = SqlAlchemyVisualTraceRepository(session)._fence(lease)
            repository = SqlAlchemyVisionRepository(session)
            state = SqlAlchemyVisualTraceRepository(session)._legacy_ref(
                VisualExplorationStateModel,
                lease.scope,
                state_id,
            )
            for proposal_id, sequence, safe_action, edge in candidates:
                repository.add_action(
                    VisualActionProposalModel(
                        id=proposal_id,
                        tenant_id=record.tenant_id,
                        session_id=record.id,
                        originating_state_id=state_id,
                        correlation_id=record.correlation_id,
                        sequence=sequence,
                        action=safe_action,
                        evidence_checksum=state.screenshot_checksum,
                        policy_version=record.policy_version,
                        provider=record.provider,
                        model=record.model,
                        prompt_version=record.prompt_version,
                    )
                )
                repository.add_trajectory_edge(edge)
                self._progress(
                    session,
                    lease,
                    "edge.proposed",
                    f"edge.proposed:{edge.id}",
                    {"action_sequence": sequence, "action_kind": safe_action["kind"]},
                )

    def finish_edge(self, lease, edge):
        with transactional_session(self._factory) as session:
            SqlAlchemyVisualTraceRepository(session)._fence(lease)
            SqlAlchemyVisionRepository(session).add_trajectory_edge(edge)

    def read_frame(self, scope, frame_id):
        frame = next(
            (f for f in self.read_snapshot(scope)["frames"] if f.metadata.id == frame_id), None
        )
        if frame is None or self._store is None:
            raise ValueError("operation frame unavailable")
        return self._store.read_operation_frame(frame)

    def operation_owners(self, scope):
        with transactional_session(self._factory) as session:
            return dict(
                session.execute(
                    select(VisualOperationModel.id, VisualOperationModel.fencing_token).where(
                        *SqlAlchemyVisualTraceRepository._scope(VisualOperationModel, scope)
                    )
                ).all()
            )

    def adopt_result(self, lease, operation_id, old_token):
        """Transfer DB evidence ownership only; never authorize a browser command."""
        with transactional_session(self._factory) as session:
            repository = SqlAlchemyVisualTraceRepository(session)
            repository._fence(lease)
            model = repository._get(VisualOperationModel, lease.scope, operation_id)
            if model is None or model.fencing_token != old_token:
                raise ValueError("operation reconciliation owner mismatch")
            model.fencing_token = lease.fencing_token

    def claim(
        self,
        scope: VisualSessionScope,
        owner: UUID,
        *,
        lease_seconds: int = 30,
    ) -> VisualSessionLease | None:
        with transactional_session(self._factory) as session:
            return SqlAlchemyVisualTraceRepository(session).claim(
                scope,
                owner,
                lease_seconds=lease_seconds,
            )

    def renew(self, lease: VisualSessionLease, *, lease_seconds: int = 30) -> VisualSessionLease:
        with transactional_session(self._factory) as session:
            return SqlAlchemyVisualTraceRepository(session).renew(
                lease, lease_seconds=lease_seconds
            )

    def commit_prepared(
        self, lease: VisualSessionLease, operation: VisualOperation
    ) -> VisualOperation:
        with transactional_session(self._factory) as session:
            return SqlAlchemyVisualTraceRepository(session).prepare(lease, operation)

    def commit_captured(
        self,
        lease: VisualSessionLease,
        record: VisualOperationFrameRecord,
        content: bytes,
        operation: VisualOperation,
        locator: VisualLocatorEvidence | None = None,
        *,
        checkpoint: VisualCheckpoint | None = None,
        semantic_change: str = "unavailable",
        duration_ms: int = 0,
    ) -> VisualOperation:
        frame = record.metadata
        if (
            frame.operation_id != operation.id
            or getattr(operation, f"actual_{frame.role}_frame_id") != frame.id
        ):
            raise ValueError("captured frame must be linked by the committed operation")
        if (frame.tenant_id, frame.project_id, frame.session_id) != (
            lease.scope.tenant_id,
            lease.scope.project_id,
            lease.scope.session_id,
        ):
            raise ValueError("captured frame scope mismatch")
        if len(content) != frame.byte_count or sha256(content).hexdigest() != frame.checksum:
            raise ValueError("operation frame bytes fail checksum/size verification")
        if self._store is None:
            raise ValueError("private operation evidence store unavailable")
        # Store implements create-only writes. A failed DB commit leaves a known, deterministic
        # orphan key; callers retain staging until this method acknowledges the commit.
        self._store.write_operation_frame(record, content)
        if self._store.read_operation_frame(record) != content:
            raise ValueError("durable operation frame failed read-back verification")
        with transactional_session(self._factory) as session:
            repository = SqlAlchemyVisualTraceRepository(session)
            repository.add_frame(lease, record)
            if locator is not None:
                repository.add_locator(lease, locator)
            saved = repository.save_operation(lease, operation)
            self._observe(session, lease, saved, checkpoint, semantic_change, duration_ms)
            if locator:
                stage = "locator.verified" if locator.status == "verified" else "locator.unresolved"
                self._progress(
                    session,
                    lease,
                    stage,
                    f"{stage}:{operation.id}",
                    {"operation_id": str(operation.id)},
                )
            return saved

    def commit_operation(
        self, lease: VisualSessionLease, operation: VisualOperation
    ) -> VisualOperation:
        with transactional_session(self._factory) as session:
            saved = SqlAlchemyVisualTraceRepository(session).save_operation(lease, operation)
            self._observe(session, lease, saved, None, "unavailable", 0)
            return saved

    def _observe(self, session, lease, operation, checkpoint, semantic_change, duration_ms):
        stage = f"operation.{operation.status}"
        self._progress(
            session,
            lease,
            stage,
            f"{stage}:{operation.id}",
            {
                "operation_id": str(operation.id),
                "operation_sequence": operation.sequence,
                "purpose": operation.purpose,
            },
        )
        if operation.status in {"prepared", "executing"}:
            return
        repository = SqlAlchemyVisualTraceRepository(session)
        legacy = SqlAlchemyVisionRepository(session)
        child = None
        if checkpoint and operation.status == "completed" and operation.actual_after_frame_id:
            if operation.purpose not in {"explore", "setup"}:
                raise ValueError("only logical exploration operations create states")
            after = next(
                f
                for f in repository.snapshot(lease.scope)["frames"]
                if f.metadata.id == operation.actual_after_frame_id
            )
            parent = repository._legacy_ref(
                VisualExplorationStateModel, lease.scope, operation.state_id
            )
            existing = session.get(VisualExplorationStateModel, checkpoint.state_id)
            if existing is None:
                legacy.add_state(
                    VisualExplorationStateModel(
                        id=checkpoint.state_id,
                        tenant_id=lease.scope.tenant_id,
                        session_id=lease.scope.session_id,
                        parent_id=operation.state_id,
                        hop=parent.hop + 1 if parent else 0,
                        screenshot_checksum=after.metadata.checksum,
                    )
                )
            repository.save_checkpoint(lease, checkpoint)
            child = checkpoint.state_id
        if operation.edge_id:
            edge = next(
                e
                for e in legacy.list_trajectory_edges(lease.scope.tenant_id, lease.scope.session_id)
                if e.id == operation.edge_id
            )
            if edge.status == "proposed":
                unchanged = (
                    operation.url_change == "unchanged"
                    and semantic_change == "unchanged"
                    and operation.visual_change == "unchanged"
                )
                legacy.add_trajectory_edge(
                    replace(
                        edge,
                        status=("no_meaningful_change" if unchanged else "observed")
                        if child
                        else "failed",
                        outcome_code=None if child else "candidate_rejected",
                        child_state_id=child,
                        observed_at=operation.ended_at if child else None,
                        duration_ms=duration_ms,
                        url_fingerprint=checkpoint.url_fingerprint if child else None,
                        url_change=operation.url_change,
                        child_screenshot_checksum=after.metadata.checksum if child else None,
                    )
                )

    def commit_checkpoint(self, lease: VisualSessionLease, checkpoint: VisualCheckpoint) -> None:
        with transactional_session(self._factory) as session:
            SqlAlchemyVisualTraceRepository(session).save_checkpoint(lease, checkpoint)

    def commit_handoff(
        self,
        lease: VisualSessionLease,
        handoff: VisualLocatorHandoff,
    ) -> VisualLocatorHandoff:
        with transactional_session(self._factory) as session:
            return SqlAlchemyVisualTraceRepository(session).add_handoff(lease, handoff)

    def read_snapshot(self, scope: VisualSessionScope) -> dict[str, tuple]:
        with transactional_session(self._factory) as session:
            # PostgreSQL READ COMMITTED would allow the four queries to see different commits.
            session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            return SqlAlchemyVisualTraceRepository(session).snapshot(scope)

    def tombstone_frame(self, scope: VisualSessionScope, frame_id: UUID) -> bool:
        with transactional_session(self._factory) as session:
            return SqlAlchemyVisualTraceRepository(session).tombstone_frame(scope, frame_id)
