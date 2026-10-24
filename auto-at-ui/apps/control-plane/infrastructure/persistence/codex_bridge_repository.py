"""Short, fenced transactions for safe bridge metadata and progress only."""

from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta

from auto_at.contracts.codex_bridge import CodexConsentSnapshot, CodexUsage, content_hash
from domain.activity import ActivityEvent
from domain.codex_bridge import (
    TERMINAL_JOB_STATUSES,
    validate_job_update,
    validate_request_time,
    validate_response,
)
from domain.entities import CodexBridgeJob
from sqlalchemy import select

from infrastructure.persistence.models import CodexBridgeJobModel
from infrastructure.persistence.repositories import (
    SqlAlchemyActivityEventRepository,
    SqlAlchemyVisualTraceRepository,
)
from infrastructure.persistence.session import transactional_session


class SqlAlchemyCodexBridgeJobRepository:
    def __init__(self, session):
        self.session = session

    @staticmethod
    def _record(row):
        if row is None:
            return None
        values = {key: getattr(row, key) for key in CodexBridgeJob.__dataclass_fields__}
        if values["usage"] is not None:
            values["usage"] = CodexUsage.model_validate(values["usage"])
        return CodexBridgeJob(**values)

    def _row(self, scope, job_id):
        return self.session.scalar(
            select(CodexBridgeJobModel)
            .where(
                CodexBridgeJobModel.job_id == job_id,
                *SqlAlchemyVisualTraceRepository._scope(CodexBridgeJobModel, scope),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def add(self, job):
        values = asdict(job)
        values["usage"] = job.usage.model_dump(mode="json") if job.usage else None
        self.session.add(CodexBridgeJobModel(**values))
        self.session.flush()

    def get(self, scope, job_id):
        return self._record(self._row(scope, job_id))

    def transition(self, old, new):
        from domain.vision import VisualSessionScope

        row = self._row(
            VisualSessionScope(old.tenant_id, old.project_id, old.session_id), old.job_id
        )
        if self._record(row) != old:
            raise ValueError("bridge job changed concurrently")
        validate_job_update(old, new)
        for key in (
            "status",
            "updated_at",
            "response_hash",
            "safe_reason",
            "cli_version",
            "actual_model",
        ):
            setattr(row, key, getattr(new, key))
        row.usage = new.usage.model_dump(mode="json") if new.usage else None
        self.session.flush()

    def pending(self, scope):
        rows = self.session.scalars(
            select(CodexBridgeJobModel)
            .where(
                *SqlAlchemyVisualTraceRepository._scope(CodexBridgeJobModel, scope),
                CodexBridgeJobModel.status.not_in(TERMINAL_JOB_STATUSES),
            )
            .with_for_update()
        ).all()
        return [self._record(row) for row in rows]

    def interrupt_pending(self, scope):
        for job in self.pending(scope):
            self.transition(
                job,
                replace(
                    job,
                    status="cancelled",
                    updated_at=datetime.now(UTC),
                    safe_reason="bridge_interrupted",
                ),
            )


class SqlAlchemyCodexJobGateway:
    def __init__(self, factory, lease):
        self.factory, self.lease = factory, lease

    def _fence(self, session, request):
        row = SqlAlchemyVisualTraceRepository(session)._fence(self.lease)
        now = datetime.now(UTC)
        validate_request_time(request, now)
        if (
            row.state != "running"
            or row.provider != "codex_cli"
            or row.model != request.model
            or row.id != request.session_id
            or row.tenant_id != request.tenant_id
            or row.project_id != request.project_id
            or row.correlation_id != request.correlation_id
            or row.fencing_token != request.fencing_token
            or request.request_sequence > row.max_steps
            or request.deadline > row.updated_at + timedelta(seconds=row.max_session_seconds)
        ):
            raise ValueError("bridge session fence rejected")
        frozen = CodexConsentSnapshot.model_validate(row.model_input_policy)
        if (
            not frozen.dom_transfer_accepted
            or request.consent.max_dom_bytes > frozen.max_dom_bytes
            or request.consent.max_dom_elements > frozen.max_dom_elements
            or request.consent.raw_screenshot_transfer_accepted
            and not frozen.raw_screenshot_transfer_accepted
        ):
            raise ValueError("bridge consent exceeds frozen session policy")
        return row

    @staticmethod
    def _event(session, request, stage, reason=None, *, key_suffix=""):
        metadata = {
            "job_id": str(request.job_id),
            "call_sequence": request.request_sequence,
            "mode": request.stage,
            "elapsed_ms": min(
                3_600_000,
                max(
                    0,
                    int(
                        (datetime.now(UTC) - request.created_at).total_seconds() * 1000,
                    ),
                ),
            ),
        }
        if reason:
            metadata["reason_code"] = reason
        SqlAlchemyActivityEventRepository(session).append(
            ActivityEvent.create_vision_progress(
                tenant_id=request.tenant_id,
                correlation_id=request.correlation_id,
                visual_exploration_session_id=request.session_id,
                stage=f"codex.{stage}",
                progress_key=f"codex:{request.job_id}:{stage}{key_suffix}",
                occurred_at=datetime.now(UTC),
                metadata=metadata,
            )
        )

    def _job(self, repository, request):
        job = repository.get(self.lease.scope, request.job_id)
        if job is None or job.request_hash != content_hash(request):
            raise ValueError("bridge job identity mismatch")
        return job

    async def register(self, request):
        with transactional_session(self.factory) as session:
            self._fence(session, request)
            repository = SqlAlchemyCodexBridgeJobRepository(session)
            if repository.get(self.lease.scope, request.job_id) is not None:
                raise ValueError("duplicate bridge publication")
            repository.add(
                CodexBridgeJob(
                    **{
                        key: getattr(request, key)
                        for key in (
                            "job_id",
                            "bridge_id",
                            "tenant_id",
                            "project_id",
                            "session_id",
                            "correlation_id",
                            "fencing_token",
                            "request_sequence",
                            "observation_id",
                            "snapshot_id",
                            "state_fingerprint",
                            "stage",
                            "deadline",
                            "created_at",
                        )
                    },
                    request_hash=content_hash(request),
                    dom_sha256=request.inputs.dom_sha256,
                    dom_element_count=request.dom_element_count,
                    updated_at=request.created_at,
                )
            )
            if request.stage == "image":
                self._event(session, request, "image_requested")
            self._event(session, request, "queued")

    async def poll(self, request, stages):
        with transactional_session(self.factory) as session:
            self._fence(session, request)
            repository = SqlAlchemyCodexBridgeJobRepository(session)
            job = self._job(repository, request)
            if job.status in TERMINAL_JOB_STATUSES:
                raise ValueError("bridge job is terminal")
            for receipt in stages:
                if receipt.job_id != job.job_id:
                    raise ValueError("bridge receipt identity mismatch")
                if (job.status, receipt.stage) in {("queued", "claimed"), ("claimed", "running")}:
                    updated = replace(job, status=receipt.stage, updated_at=datetime.now(UTC))
                    repository.transition(job, updated)
                    job = updated
                    if receipt.stage == "running":
                        self._event(session, request, "started")

    async def finish(self, request, response):
        with transactional_session(self.factory) as session:
            self._fence(session, request)
            validate_response(request, response, now=datetime.now(UTC))
            repository = SqlAlchemyCodexBridgeJobRepository(session)
            job = self._job(repository, request)
            if job.status in TERMINAL_JOB_STATUSES:
                raise ValueError("bridge result already consumed")
            if response.output and job.status != "running":
                raise ValueError("bridge result has no verified running receipt")
            self._event(session, request, "validating")
            repository.transition(
                job,
                replace(
                    job,
                    status="failed" if response.failure_code else "completed",
                    updated_at=datetime.now(UTC),
                    response_hash=content_hash(response),
                    safe_reason=response.failure_code,
                    usage=response.usage,
                    cli_version=response.cli_version,
                    actual_model=response.actual_model,
                ),
            )
            self._event(
                session,
                request,
                "failed" if response.failure_code else "completed",
                response.failure_code,
            )

    async def cancel(self, request, reason):
        with transactional_session(self.factory) as session:
            # Terminalization is allowed after expiry/revocation, but only this exact job.
            repository = SqlAlchemyCodexBridgeJobRepository(session)
            job = self._job(repository, request)
            if job.status in TERMINAL_JOB_STATUSES:
                return
            repository.transition(
                job,
                replace(job, status="cancelled", updated_at=datetime.now(UTC), safe_reason=reason),
            )
            self._event(session, request, "failed", reason)

    async def cleanup_pending(self, request):
        with transactional_session(self.factory) as session:
            self._job(SqlAlchemyCodexBridgeJobRepository(session), request)
            self._event(session, request, "failed", "bridge_cleanup_pending", key_suffix=":cleanup")
