"""Commit intent and real evidence around each primitive; never redispatch uncertainty."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
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


def evolve(value, **changes):
    return type(value).model_validate(value.model_dump() | changes)


class VisualOperationStopped(RuntimeError):
    """Safe terminal reason; previously committed evidence remains available."""


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
    ) -> None:
        self.uow, self.worker, self.lease = uow, worker, lease
        self.deadline, self.max_operations, self.max_frame_bytes = (
            deadline,
            max_operations,
            max_frame_bytes,
        )
        self.check_policy = check_policy
        self.identity = VisualWorkerIdentity(
            tenant_id=lease.scope.tenant_id,
            project_id=lease.scope.project_id,
            session_id=lease.scope.session_id,
            fencing_token=lease.fencing_token,
        )

    def guard(self):
        if datetime.now(UTC) >= self.deadline:
            raise VisualOperationStopped("session_timeout")
        self.check_policy()
        self.lease = self.uow.renew(self.lease)

    async def bounded(self, call):
        remaining = (self.deadline - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            raise VisualOperationStopped("session_timeout")
        task = asyncio.create_task(call())
        try:
            async with asyncio.timeout(remaining):
                while True:
                    done, _ = await asyncio.wait({task}, timeout=10)
                    if done:
                        return task.result()
                    self.lease = self.uow.renew(self.lease)
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

    async def _capture(self, operation, result, role):
        metadata = next((frame for frame in result.frames if frame.role == role), None)
        reference = getattr(operation, f"actual_{role}_frame_id")
        if (metadata is None) != (reference is None):
            raise VisualOperationStopped("worker_frame_missing")
        if metadata is None:
            return self.uow.commit_operation(self.lease, operation)
        if metadata.byte_count > self.max_frame_bytes:
            raise VisualOperationStopped("screenshot_byte_limit")
        content = await self.bounded(lambda: self.worker.frame(self.identity, metadata))
        signature = (
            b"\x89PNG\r\n\x1a\n" if metadata.content_type == "image/png" else b"\xff\xd8\xff"
        )
        if not content.startswith(signature):
            raise VisualOperationStopped("capture_type_invalid")
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
        try:
            try:
                result = await self.bounded(lambda: self.worker.prepare(request))
            except Exception:
                result = await self.bounded(lambda: self.worker.read(self.identity, intent.id))
            prepared = self._merge(current, result)
            current = await self._capture(prepared, result, "before")
            if current.status in FINAL_OPERATION_STATUSES:
                await self._ack(result)
                return result.model_copy(update={"operation": current})
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
            final = self._merge(current, result)
            if final.status not in FINAL_OPERATION_STATUSES:
                raise VisualOperationStopped("worker_response_lost")
            current = await self._capture(final, result, "after")
            await self._ack(result)
            return result.model_copy(update={"operation": current})
        except Exception as error:
            if current.status not in FINAL_OPERATION_STATUSES:
                self._stop(
                    current,
                    "worker_response_lost" if dispatched else "prepare_unavailable",
                    unknown=dispatched,
                )
            if isinstance(error, VisualOperationStopped):
                raise
            raise VisualOperationStopped("operation_unavailable") from None

    async def reconcile(self, operation: VisualOperation):
        """Read-only reconciliation; RAM loss never reconstructs input or repeats a side effect."""
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
                operation = await self._capture(final, result, "after")
            else:
                raise VisualOperationStopped("worker_response_lost")
            await self._ack(result)
            return result.model_copy(update={"operation": final})
        except Exception:
            if operation.status not in FINAL_OPERATION_STATUSES:
                self._stop(operation, "worker_response_lost", unknown=True)
            raise VisualOperationStopped("worker_state_unavailable") from None
