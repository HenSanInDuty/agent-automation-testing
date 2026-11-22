"""Commit intent and real evidence around each primitive; never redispatch uncertainty."""

import asyncio
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from auto_at.contracts.vision import VisualOperation
from auto_at.contracts.vision_worker import (
    VisualWorkerAck,
    VisualWorkerExecute,
    VisualWorkerIdentity,
    VisualWorkerPrepare,
)
from domain.entities import VisualOperationFrameRecord
from domain.ports import VisualTraceUnitOfWork, VisualWorkerTransport
from domain.vision import FINAL_OPERATION_STATUSES, VisualSessionLease

logger = logging.getLogger(__name__)
_SAFE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
# Allowlisted stages only; anything else is reported as "unclassified".
FAILURE_STAGES = frozenset({
    "prepare", "capture_before", "execute", "merge", "capture_after", "ack",
    "frame_limit", "frame_fetch", "frame_signature",
    "store_write", "store_readback",
    "db_commit", "db_frame", "db_locator", "db_operation", "db_observe",
    "db_checkpoint", "db_edge", "db_progress", "unclassified",
})


def evolve(value, **changes):
    return type(value).model_validate(value.model_dump() | changes)


class VisualOperationStopped(RuntimeError):
    """Safe terminal reason; previously committed evidence remains available."""


def _staged(error, stage):
    """Attach the first failure stage to an exception without changing its type."""
    if getattr(error, "failure_stage", None) is None:
        try:
            error.failure_stage = stage
        except Exception:  # pragma: no cover - exotic exception without __dict__
            pass
    return error


class ExecuteVisualOperation:
    def __init__(
        self,
        uow: VisualTraceUnitOfWork,
        worker: VisualWorkerTransport,
        lease: VisualSessionLease,
        deadline: datetime,
        max_operations: int,
        max_frame_bytes: int,
        check_policy: Callable[[], None],
        step_timeout_seconds: float | None = None,
    ) -> None:
        self.uow, self.worker, self.lease = uow, worker, lease
        self.deadline, self.max_operations, self.max_frame_bytes = (
            deadline,
            max_operations,
            max_frame_bytes,
        )
        self.check_policy = check_policy
        self.step_timeout_seconds = step_timeout_seconds
        self.operation_deadline = None
        self.deadline_ceiling = None
        self.last_failure: dict[str, str | int] | None = None
        self.identity = VisualWorkerIdentity(
            tenant_id=lease.scope.tenant_id,
            project_id=lease.scope.project_id,
            session_id=lease.scope.session_id,
            fencing_token=lease.fencing_token,
        )

    def guard(self):
        limit = self.operation_deadline or (self.deadline if self.step_timeout_seconds is None
                                            else None)
        if self.deadline_ceiling is not None:
            limit = min(limit, self.deadline_ceiling) if limit else self.deadline_ceiling
        if limit is not None and datetime.now(UTC) >= limit:
            raise VisualOperationStopped(
                "step_timeout" if self.step_timeout_seconds is not None else "session_timeout",
            )
        self.check_policy()
        self.lease = self.uow.renew(self.lease)

    async def bounded(self, call):
        deadline = self.operation_deadline or (
            datetime.now(UTC) + timedelta(seconds=self.step_timeout_seconds)
            if self.step_timeout_seconds is not None else self.deadline
        )
        if self.deadline_ceiling is not None:
            deadline = min(deadline, self.deadline_ceiling)
        remaining = (deadline - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            raise VisualOperationStopped(
                "step_timeout" if self.step_timeout_seconds is not None else "session_timeout",
            )
        task = asyncio.create_task(call())
        try:
            async with asyncio.timeout(remaining):
                while True:
                    done, _ = await asyncio.wait({task}, timeout=10)
                    if done:
                        return task.result()
                    self.check_policy()
                    self.lease = self.uow.renew(self.lease)
        except TimeoutError:
            raise VisualOperationStopped(
                "step_timeout" if self.step_timeout_seconds is not None else "session_timeout",
            ) from None
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    def _merge(self, intent, result):
        remote = result.operation
        for key in (
            "id",
            "tenant_id",
            "project_id",
            "session_id",
            "sequence",
            "purpose",
            "action_kind",
            "state_id",
            "proposal_id",
            "checkpoint_id",
            "parent_operation_id",
            "expected_parent_fingerprint",
        ):
            if getattr(remote, key) != getattr(intent, key):
                raise VisualOperationStopped("worker_result_mismatch")
        # The control-plane timestamp is the persisted dispatch intent, preceding capture.
        return evolve(remote, started_at=intent.started_at, edge_id=intent.edge_id,
                      attempt=intent.attempt)

    def _stop(self, operation, code, *, unknown=False):
        return self.uow.commit_operation(
            self.lease,
            evolve(
                operation,
                status="unknown" if unknown else "failed",
                ended_at=datetime.now(UTC),
                outcome_code=code,
                before_unavailable_reason=None if operation.actual_before_frame_id else code,
                after_unavailable_reason=None if operation.actual_after_frame_id else code,
            ),
        )

    def _diagnose(self, error, phase, operation, outcome_code):
        """Record a typed, secret-free failure classification; never the message or traceback."""
        stage = getattr(error, "failure_stage", None) or phase
        name = type(error).__name__
        module = type(error).__module__.split(".", 1)[0]
        self.last_failure = {
            "failure_stage": stage if stage in FAILURE_STAGES else "unclassified",
            "error_type": name if _SAFE_NAME.fullmatch(name) else "unclassified",
            "error_module": module if _SAFE_NAME.fullmatch(module) else "unclassified",
            "operation_id": str(operation.id),
            "operation_sequence": operation.sequence,
            "outcome_code": outcome_code,
        }
        logger.warning(
            "Vision operation outcome could not be proven.",
            extra={"event": "vision.operation.failure_stage", **self.last_failure},
        )

    async def _capture(self, operation, result, role):
        metadata = next((frame for frame in result.frames if frame.role == role), None)
        reference = getattr(operation, f"actual_{role}_frame_id")
        if (metadata is None) != (reference is None):
            raise VisualOperationStopped("worker_frame_missing")
        if metadata is None:
            return self.uow.commit_operation(self.lease, operation)
        if metadata.byte_count > self.max_frame_bytes:
            raise _staged(VisualOperationStopped("screenshot_byte_limit"), "frame_limit")
        try:
            content = await self.bounded(lambda: self.worker.frame(self.identity, metadata))
        except Exception as error:
            _staged(error, "frame_fetch")
            raise
        signature = (
            b"\x89PNG\r\n\x1a\n" if metadata.content_type == "image/png" else b"\xff\xd8\xff"
        )
        if not content.startswith(signature):
            raise _staged(VisualOperationStopped("capture_type_invalid"), "frame_signature")
        tenant = sha256(metadata.tenant_id.encode()).hexdigest()
        record = VisualOperationFrameRecord(
            metadata,
            (
                f"vision-operations/{tenant}/{metadata.project_id}/{metadata.session_id}/"
                f"{metadata.operation_id}/{role}"
            ),
        )
        return self.uow.commit_captured(
            self.lease,
            record,
            content,
            operation,
            result.locator if role == "before" else None,
            checkpoint=result.checkpoint if role == "after" else None,
            semantic_change=result.semantic_change, duration_ms=result.duration_ms,
        )

    async def _ack(self, result):
        try:
            await self.bounded(
                lambda: self.worker.acknowledge(
                    VisualWorkerAck(
                        **self.identity.model_dump(),
                        operation_id=result.operation.id,
                        persisted_frame_ids=tuple(frame.id for frame in result.frames),
                    )
                )
            )
        except Exception:
            # No subsequent primitive should grow staging after cleanup failed.
            raise VisualOperationStopped("frame_ack_unavailable") from None

    async def execute(self, intent: VisualOperation, request: VisualWorkerPrepare):
        self.guard()
        if intent.sequence > self.max_operations:
            raise VisualOperationStopped("operation_budget_exhausted")
        if request.operation_id != intent.id or any(
            getattr(request, key) != value for key, value in self.identity.model_dump().items()
        ):
            raise ValueError("operation request identity mismatch")
        snapshot = self.uow.read_snapshot(self.lease.scope)
        existing = next((op for op in snapshot["operations"] if op.id == intent.id), None)
        if existing is not None:
            # Retry callers can inspect the committed result, but cannot re-click.
            return await self.reconcile(existing)
        if any(op.status in {"prepared", "executing", "unknown"} for op in snapshot["operations"]):
            raise VisualOperationStopped("previous_operation_unresolved")
        current = self.uow.commit_prepared(self.lease, intent)
        dispatched = False
        phase = "prepare"
        if self.step_timeout_seconds is not None:
            self.operation_deadline = datetime.now(UTC) + timedelta(
                seconds=self.step_timeout_seconds,
            )
            if self.deadline_ceiling is not None:
                self.operation_deadline = min(self.operation_deadline, self.deadline_ceiling)
            request = evolve(request, step_deadline=self.operation_deadline)
        try:
            try:
                result = await self.bounded(lambda: self.worker.prepare(request))
            except Exception:
                result = await self.bounded(lambda: self.worker.read(self.identity, intent.id))
            phase = "merge"
            prepared = self._merge(current, result)
            phase = "capture_before"
            current = await self._capture(prepared, result, "before")
            if current.status in FINAL_OPERATION_STATUSES:
                phase = "ack"
                await self._ack(result)
                return result.model_copy(update={"operation": current})
            phase = "execute"
            self.guard()
            current = self.uow.commit_operation(self.lease, evolve(current, status="executing"))
            before = next(frame for frame in result.frames if frame.role == "before")
            command = VisualWorkerExecute(
                **self.identity.model_dump(),
                operation_id=intent.id,
                prepared_handle=result.prepared_handle,
                before_frame_id=before.id,
                before_checksum=before.checksum,
                before_persisted=True,
            )
            dispatched = True
            try:
                result = await self.bounded(lambda: self.worker.execute(command))
            except Exception:
                # Read the same operation only. Never repeat execute after a lost response.
                result = await self.bounded(lambda: self.worker.read(self.identity, intent.id))
            phase = "merge"
            final = self._merge(current, result)
            if final.status not in FINAL_OPERATION_STATUSES:
                raise VisualOperationStopped("worker_response_lost")
            phase = "capture_after"
            current = await self._capture(final, result, "after")
            phase = "ack"
            await self._ack(result)
            return result.model_copy(update={"operation": current})
        except Exception as error:
            if current.status not in FINAL_OPERATION_STATUSES:
                code = (
                    "step_timeout" if isinstance(error, VisualOperationStopped)
                    and str(error) == "step_timeout"
                    else "worker_response_lost" if dispatched else "prepare_unavailable"
                )
                self._diagnose(error, phase, current, code)
                self._stop(current, code, unknown=dispatched)
            if isinstance(error, VisualOperationStopped):
                raise
            raise VisualOperationStopped("operation_unavailable") from None
        finally:
            self.operation_deadline = None

    async def reconcile(self, operation: VisualOperation):
        """Read-only reconciliation; RAM loss never reconstructs input or repeats a side effect."""
        phase = "merge"
        try:
            result = await self.bounded(lambda: self.worker.read(self.identity, operation.id))
            final = self._merge(operation, result)
            if operation.status in FINAL_OPERATION_STATUSES:
                if operation != final:
                    raise VisualOperationStopped("worker_result_mismatch")
            elif final.status in FINAL_OPERATION_STATUSES:
                # A prepared record has not authorized browser execution.
                if operation.status != "executing":
                    raise VisualOperationStopped("prepared_operation_abandoned")
                phase = "capture_after"
                operation = await self._capture(final, result, "after")
            else:
                raise VisualOperationStopped("worker_response_lost")
            phase = "ack"
            await self._ack(result)
            return result.model_copy(update={"operation": final})
        except Exception as error:
            if operation.status not in FINAL_OPERATION_STATUSES:
                self._diagnose(error, phase, operation, "worker_response_lost")
                self._stop(operation, "worker_response_lost", unknown=True)
            raise VisualOperationStopped("worker_state_unavailable") from None
