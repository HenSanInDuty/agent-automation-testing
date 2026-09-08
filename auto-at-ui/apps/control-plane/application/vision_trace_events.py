"""Live v4 BFS exploration using detached records and commit-per-operation ports."""

import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from agents.prompts.vision import VISION_PROMPT_VERSION
from agents.shared.runtime import AgentStepGuard, resolve_agent_runtime
from agents.vision.executor import policy_to_step_guard
from agents.vision.intent import decrypt_visual_intent
from auto_at.contracts.generation import ProjectExecutionPolicy
from auto_at.contracts.vision import VisualOperation
from auto_at.contracts.vision_worker import (
    VisualWorkerAction,
    VisualWorkerOpen,
    VisualWorkerPrepare,
)
from domain.entities import VisualTrajectoryEdgeRecord
from domain.ports import VisualTraceUnitOfWork, VisualWorkerTransport
from domain.vision import VisualSessionScope

from application.vision_handoff import build_vision_handoff
from application.vision_operations import ExecuteVisualOperation, VisualOperationStopped, evolve


@dataclass
class Branch:
    state_id: UUID
    checkpoint: object
    hop: int
    path: tuple
    result: object


class VisionTraceEventProcessor:
    def __init__(
        self, uow: VisualTraceUnitOfWork, worker: VisualWorkerTransport, settings, model_batch
    ):
        self.uow, self.worker, self.settings, self.model_batch = uow, worker, settings, model_batch

    async def execute(self, event):
        if event.event_type != "agent.visual_exploration.requested.v1":
            raise ValueError("unexpected visual event")
        record = self.uow.get_session(event.tenant_id, UUID(event.payload["session_id"]))
        if record is None or record.state in {"completed", "unavailable", "cancelled"}:
            return "already_processed"
        if record.trace_version != "v4":
            raise ValueError("v4 processor requires a v4 session")
        scope = VisualSessionScope(record.tenant_id, record.project_id, record.id)
        lease = self.uow.claim(scope, uuid4())
        if lease is None:
            return "busy"
        previous_state = record.state
        record = self.uow.running(lease, VISION_PROMPT_VERSION)
        _, config, policy = self.uow.context(scope)
        runtime = resolve_agent_runtime(self.settings, config).vision
        deadline = record.updated_at + timedelta(
            seconds=min(
                record.max_session_seconds,
                runtime.max_session_seconds,
            )
        )
        max_states = min(record.max_states, policy.vision_max_states) if policy else 0
        max_hops = min(record.max_hops, policy.vision_max_hops) if policy else 0
        calls = 0

        def check_policy():
            current, config, latest = self.uow.context(scope)
            live = resolve_agent_runtime(self.settings, config).vision
            if (
                current.state != "running"
                or not live.enabled
                or not live.raw_screenshot_transfer_accepted
                or latest is None
                or live.provider != record.provider
                or live.model != record.model
                or not ProjectExecutionPolicy(
                    project_id=record.project_id, allowed_origins=latest.allowed_origins
                ).allows(record.target_url)
                or latest.allowed_origins != policy.allowed_origins
            ):
                raise VisualOperationStopped("policy_disabled")
            if datetime.now(UTC) >= record.updated_at + timedelta(
                seconds=min(
                    live.max_session_seconds,
                    record.max_session_seconds,
                )
            ):
                raise VisualOperationStopped("session_timeout")
            return live, latest

        operations = ExecuteVisualOperation(
            self.uow,
            self.worker,
            lease,
            deadline,
            1 + max_states * (2 * max_hops + 3),
            min(record.max_screenshot_bytes, runtime.max_screenshot_bytes),
            check_policy,
        )
        opened = False
        try:
            if previous_state == "running" or lease.fencing_token > 1:
                # Recovery is evidence-only: the BFS queue and input values are memory-only.
                operations.deadline = datetime.now(UTC) + timedelta(seconds=20)
                owners = self.uow.operation_owners(scope)
                for operation in self.uow.read_snapshot(scope)["operations"]:
                    old_token = owners[operation.id]
                    operations.identity = evolve(operations.identity, fencing_token=old_token)
                    try:
                        result = await operations.bounded(
                            lambda operation=operation: self.worker.read(
                                operations.identity,
                                operation.id,
                            )
                        )
                        operations._merge(operation, result)
                        if result.operation.status in {
                            "completed",
                            "failed",
                            "rejected",
                            "unknown",
                        }:
                            self.uow.adopt_result(operations.lease, operation.id, old_token)
                        await operations.reconcile(operation)
                    except Exception:
                        if operation.status in {"prepared", "executing"}:
                            operations._stop(operation, "worker_state_unavailable", unknown=True)
                return self.uow.finish(operations.lease, "worker_state_unavailable")
            check_policy()
            if not max_states or not max_hops or not self.settings.vision_worker_secret:
                raise VisualOperationStopped("worker_unavailable")
            intent = decrypt_visual_intent(
                record.encrypted_task_intent,
                self.settings.vision_intent_encryption_key,
                record.intent_retention_until,
            )
            opened = True
            fingerprint = await operations.bounded(
                lambda: self.worker.open(
                    VisualWorkerOpen(
                        **operations.identity.model_dump(),
                        target_url=record.target_url,
                        allowed_origins=tuple(policy.allowed_origins),
                        deadline=deadline,
                        max_session_seconds=min(
                            record.max_session_seconds, runtime.max_session_seconds
                        ),
                        max_states=max_states,
                        max_hops=max_hops,
                        max_screenshot_bytes=operations.max_frame_bytes,
                    )
                )
            )
            sequence, proposal_sequence, visited = 0, 0, 0
            browser_parent = None
            requests, results = {}, {}

            async def primitive(
                action,
                purpose,
                *,
                state=None,
                proposal=None,
                edge=None,
                checkpoint_id=None,
                checkpoint_state_id=None,
                restore=None,
                replay=None,
            ):
                nonlocal sequence, fingerprint, browser_parent
                live, _ = check_policy()
                operations.max_frame_bytes = min(
                    operations.max_frame_bytes, live.max_screenshot_bytes
                )
                sequence += 1
                command = VisualWorkerPrepare(
                    **operations.identity.model_dump(),
                    operation_id=uuid4(),
                    purpose=purpose,
                    action=action,
                    expected_state_fingerprint=fingerprint,
                    state_id=state,
                    proposal_id=proposal,
                    checkpoint_id=checkpoint_id,
                    checkpoint_state_id=checkpoint_state_id,
                    restore_checkpoint_id=restore.id if restore else None,
                    replay_operation_id=replay.operation.id if replay else None,
                    expected_locator=replay.locator.descriptor
                    if replay and replay.locator
                    else None,
                    model_confidence=edge.confidence if edge else 0,
                )
                operation = VisualOperation(
                    id=command.operation_id,
                    tenant_id=scope.tenant_id,
                    project_id=scope.project_id,
                    session_id=scope.session_id,
                    sequence=sequence,
                    purpose=purpose,
                    action_kind=action.kind,
                    state_id=state,
                    proposal_id=proposal,
                    checkpoint_id=restore.id if restore else None,
                    edge_id=edge.id if edge else None,
                    parent_operation_id=None if action.kind == "navigate" else browser_parent,
                    expected_parent_fingerprint=fingerprint,
                    started_at=datetime.now(UTC),
                    status="prepared",
                    attempt=1
                    + sum(
                        1
                        for prior in requests.values()
                        if proposal is not None and prior.proposal_id == proposal
                    ),
                )
                result = await operations.execute(operation, command)
                requests[operation.id], results[operation.id] = command, result
                fingerprint = result.state_fingerprint or fingerprint
                if result.operation.status == "unknown":
                    raise VisualOperationStopped("action_outcome_unknown")
                if result.operation.status == "completed":
                    if restore:
                        browser_parent = restore.ancestor_operation_ids[-1]
                    elif purpose in {"setup", "explore", "replay"}:
                        browser_parent = operation.id
                return result

            root_state, root_checkpoint = uuid4(), uuid4()
            root = await primitive(
                VisualWorkerAction(kind="navigate"),
                "setup",
                checkpoint_id=root_checkpoint,
                checkpoint_state_id=root_state,
            )
            if root.operation.status != "completed" or root.checkpoint is None:
                raise VisualOperationStopped("initial_capture_failed")
            visited = 1
            current = Branch(root_state, root.checkpoint, 0, (root.operation.id,), root)
            queue = []
            effective = runtime.model_copy(
                update={
                    "max_steps": min(record.max_steps, runtime.max_steps),
                    "max_screenshot_bytes": operations.max_frame_bytes,
                }
            )
            guard = AgentStepGuard(policy_to_step_guard(effective))
            last_call = None

            async def propose(branch):
                nonlocal calls, last_call, proposal_sequence
                live, latest = check_policy()
                if branch.hop >= min(max_hops, latest.vision_max_hops):
                    return
                remaining = min(max_states, latest.vision_max_states) - visited - len(queue)
                if remaining < 1 or calls >= min(record.max_steps, live.max_steps):
                    return
                if last_call is not None:
                    interval = 60 / min(
                        record.max_requests_per_minute, live.max_requests_per_minute
                    )
                    wait = interval - (datetime.now(UTC) - last_call).total_seconds()
                    if wait > 0:
                        await operations.bounded(lambda: asyncio.sleep(wait))
                live, _ = check_policy()
                image = self.uow.read_frame(scope, branch.result.operation.actual_after_frame_id)
                if len(image) > min(record.max_screenshot_bytes, live.max_screenshot_bytes):
                    raise VisualOperationStopped("screenshot_byte_limit")
                self.uow.progress(
                    operations.lease,
                    "candidate.requested",
                    f"candidate.requested:{branch.state_id}",
                    {"state_sequence": visited, "hop": branch.hop},
                )
                calls += 1
                last_call = datetime.now(UTC)
                outcome = await operations.bounded(
                    lambda: self.model_batch(
                        session=record,
                        screenshot=image,
                        task_intent=intent,
                        policy=live,
                        max_candidates=min(20, remaining),
                        guard=guard,
                        sequence=calls,
                        check_policy=check_policy,
                    )
                )
                check_policy()
                if outcome.actions is None:
                    raise VisualOperationStopped("model_unavailable")
                self.uow.progress(
                    operations.lease,
                    "candidate.received",
                    f"candidate.received:{branch.state_id}",
                    {"state_sequence": visited, "candidate_count": len(outcome.actions)},
                )
                candidates = []
                for action in outcome.actions:
                    proposal_sequence += 1
                    safe = action.model_dump(exclude={"text", "expected_outcome"})
                    proposal_id = uuid4()
                    edge = VisualTrajectoryEdgeRecord(
                        uuid4(),
                        scope.tenant_id,
                        scope.session_id,
                        branch.state_id,
                        proposal_id,
                        1,
                        safe,
                        action.confidence,
                        "proposed",
                        None,
                        None,
                        None,
                        0,
                        None,
                        "unavailable",
                        None,
                        datetime.now(UTC),
                    )
                    candidates.append((proposal_id, proposal_sequence, safe, edge))
                    queue.append((branch, action, edge))
                self.uow.proposals(operations.lease, branch.state_id, candidates)

            async def restore(branch):
                nonlocal current, browser_parent
                checkpoint, matches = await operations.bounded(
                    lambda: self.worker.checkpoint(operations.identity, branch.checkpoint.id)
                )
                if checkpoint != branch.checkpoint:
                    raise VisualOperationStopped("checkpoint_mismatch")
                if matches and browser_parent == branch.path[-1]:
                    current = branch
                    return
                self.uow.progress(
                    operations.lease, "state.restore_started", f"restore:{sequence + 1}"
                )
                if not matches:
                    popup = (
                        current.result.operation.before_page_id
                        != current.result.operation.after_page_id
                    )
                    tentative = await primitive(
                        VisualWorkerAction(kind="close_popup" if popup else "back"), "restore"
                    )
                    if tentative.operation.status == "unknown":
                        raise VisualOperationStopped("state_restore_failed")
                    _, matches = await operations.bounded(
                        lambda: self.worker.checkpoint(operations.identity, branch.checkpoint.id)
                    )
                if matches:
                    verified = await primitive(
                        VisualWorkerAction(kind="wait", duration_ms=100),
                        "restore",
                        state=branch.state_id,
                        restore=branch.checkpoint,
                    )
                else:
                    verified = None
                    for index, source_id in enumerate(branch.path):
                        source, command = results[source_id], requests[source_id]
                        if not source.replayable:
                            raise VisualOperationStopped("unsafe_replay")
                        final = index == len(branch.path) - 1
                        verified = await primitive(
                            command.action,
                            "replay",
                            state=command.state_id,
                            proposal=command.proposal_id,
                            replay=source,
                            restore=branch.checkpoint if final else None,
                        )
                        if verified.operation.status != "completed":
                            raise VisualOperationStopped("state_restore_failed")
                if verified is None or verified.operation.status != "completed":
                    raise VisualOperationStopped("state_restore_failed")
                _, matches = await operations.bounded(
                    lambda: self.worker.checkpoint(operations.identity, branch.checkpoint.id)
                )
                if not matches:
                    raise VisualOperationStopped("state_restore_failed")
                self.uow.progress(operations.lease, "state.restored", f"restored:{sequence}")
                current = branch

            await propose(current)
            while queue:
                branch, action, edge = queue.pop(0)
                if action.kind == "stop":
                    self.uow.finish_edge(
                        operations.lease,
                        replace(edge, status="terminal", outcome_code="model_stop"),
                    )
                    continue
                _, latest = check_policy()
                if visited >= min(max_states, latest.vision_max_states) or branch.hop >= min(
                    max_hops, latest.vision_max_hops
                ):
                    self.uow.finish_edge(
                        operations.lease,
                        replace(edge, status="terminal", outcome_code="state_limit"),
                    )
                    continue
                try:
                    await restore(branch)
                except Exception:
                    self.uow.progress(
                        operations.lease,
                        "state.restore_failed",
                        f"restore.failed:{sequence}",
                    )
                    raise
                child_id = uuid4()
                result = await primitive(
                    VisualWorkerAction.model_validate(
                        action.model_dump(exclude={"confidence", "expected_outcome"})
                    ),
                    "explore",
                    state=branch.state_id,
                    proposal=edge.proposal_id,
                    edge=edge,
                    checkpoint_id=uuid4(),
                    checkpoint_state_id=child_id,
                )
                if result.operation.status == "rejected":
                    continue
                if result.operation.status != "completed" or result.checkpoint is None:
                    raise VisualOperationStopped("capture_or_action_failed")
                visited += 1
                current = Branch(
                    child_id,
                    result.checkpoint,
                    branch.hop + 1,
                    (*branch.path, result.operation.id),
                    result,
                )
                await propose(current)
            handoff, handoff_reason = None, None
            try:
                handoff = build_vision_handoff(scope, self.uow.read_snapshot(scope))
            except ValueError as error:
                handoff_reason = (
                    "handoff_branch_limit"
                    if str(error) == "handoff_branch_limit"
                    else "handoff_incomplete"
                )
            return self.uow.finish(
                operations.lease, handoff=handoff, intent=intent, handoff_reason=handoff_reason
            )
        except Exception as error:
            reason = (
                str(error)
                if isinstance(error, VisualOperationStopped)
                else "visual_exploration_unavailable"
            )
            try:
                partial = build_vision_handoff(scope, self.uow.read_snapshot(scope))
            except ValueError:
                partial = None
            return self.uow.finish(operations.lease, reason, handoff=partial)
        finally:
            if opened:
                try:
                    async with asyncio.timeout(5):
                        await self.worker.close(operations.identity)
                except Exception:
                    pass
