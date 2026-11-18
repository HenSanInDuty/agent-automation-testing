"""Live v4 BFS exploration using detached records and commit-per-operation ports."""

import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from agents.prompts.vision import VISION_PROMPT_VERSION
from agents.shared.runtime import AgentStepGuard, resolve_agent_runtime
from agents.vision.executor import VisualCandidateBatchOutcome, policy_to_step_guard
from agents.vision.intent import decrypt_visual_intent
from auto_at.contracts.codex_bridge import CodexConsentSnapshot
from auto_at.contracts.vision import VisualOperation
from auto_at.contracts.vision_worker import (
    VisualWorkerAction,
    VisualWorkerCheckTarget,
    VisualWorkerObserveDom,
    VisualWorkerOpen,
    VisualWorkerPrepare,
)
from domain.entities import VisualTrajectoryEdgeRecord
from domain.ports import VisualTraceUnitOfWork, VisualWorkerTransport
from domain.vision import (
    VisionImageAuthorizationRequired,
    VisionObservationUnavailable,
    VisualSessionScope,
    vision_model_failure_reason,
)
from domain.vision_coverage import inventory, remaining_observation, target_key
from domain.vision_restoration import (
    can_refresh_undispatched_popup_close,
    can_reobserve_undispatched,
)
from domain.vision_scope import interaction_scope

from application.codex_candidates import CodexCallBudget, CodexImage, CodexUnavailable
from application.vision_handoff import build_vision_handoff
from application.vision_model_batch import VisionModelBatch, VisionModelSession
from application.vision_operations import ExecuteVisualOperation, VisualOperationStopped, evolve
from application.vision_origins import RecordVisualOrigins


@dataclass
class Branch:
    state_id: UUID
    checkpoint: object
    hop: int
    path: tuple
    result: object


class VisionTraceEventProcessor:
    def __init__(
        self,
        uow: VisualTraceUnitOfWork,
        worker: VisualWorkerTransport,
        settings,
        model_batch: VisionModelBatch,
        codex_candidates=None,
    ):
        self.uow, self.worker, self.settings, self.model_batch = uow, worker, settings, model_batch
        self.codex_candidates = codex_candidates

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
        try:
            runtime = resolve_agent_runtime(self.settings, config).vision
        except ValueError:
            return self.uow.finish(lease, "policy_disabled")
        step_timeout = getattr(record, "step_timeout_seconds", None)
        timeout_start = datetime.now(UTC) if step_timeout is not None else record.updated_at
        deadline = timeout_start + timedelta(
            seconds=min(
                step_timeout or record.max_session_seconds,
                runtime.max_session_seconds,
            )
        )
        max_states = min(record.max_states, policy.vision_max_states) if policy else 0
        max_hops = min(record.max_hops, policy.vision_max_hops) if policy else 0
        calls = 0
        model_failure = None
        frozen_input = None
        if record.provider == "codex_cli":
            try:
                frozen_input = CodexConsentSnapshot.model_validate(record.model_input_policy)
            except ValueError:
                return self.uow.finish(lease, "policy_disabled")

        def check_policy():
            current, config, latest = self.uow.context(scope)
            try:
                live = resolve_agent_runtime(self.settings, config).vision
            except ValueError:
                raise VisualOperationStopped("policy_disabled") from None
            if (
                current.state != "running"
                or not live.enabled
                or current.fencing_token != lease.fencing_token
                or (
                    record.provider != "codex_cli"
                    and (
                        not live.raw_screenshot_transfer_accepted
                        or live.raw_screenshot_transfer_provider != record.provider
                    )
                )
                or latest is None
                or live.provider != record.provider
                or live.model != record.model
            ):
                raise VisualOperationStopped("policy_disabled")
            if frozen_input is not None:
                if (
                    not frozen_input.dom_transfer_accepted
                    or live.codex is None
                    or not live.codex.dom_transfer_accepted
                ):
                    raise VisualOperationStopped("policy_disabled")
                image_allowed = (
                    frozen_input.raw_screenshot_transfer_accepted
                    and live.raw_screenshot_transfer_accepted
                )
                live = live.model_copy(
                    update={
                        "codex": live.codex.model_copy(
                            update={
                                "max_dom_bytes": min(
                                    frozen_input.max_dom_bytes, live.codex.max_dom_bytes
                                ),
                                "max_dom_elements": min(
                                    frozen_input.max_dom_elements, live.codex.max_dom_elements
                                ),
                            }
                        ),
                        "raw_screenshot_transfer_accepted": image_allowed,
                        "raw_screenshot_transfer_provider": "codex_cli" if image_allowed else None,
                    }
                )
            if step_timeout is None and datetime.now(UTC) >= record.updated_at + timedelta(
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
            step_timeout_seconds=min(step_timeout, runtime.max_session_seconds)
            if step_timeout is not None else None,
        )
        opened = False
        origins = RecordVisualOrigins(operations)
        try:
            if previous_state == "running" or lease.fencing_token > 1:
                # Recovery is evidence-only: the BFS queue and input values are memory-only.
                operations.deadline = datetime.now(UTC) + timedelta(seconds=20)
                operations.step_timeout_seconds = None
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
            target_scope = interaction_scope(intent) if frozen_input else "all"
            opened = True
            fingerprint = await operations.bounded(
                lambda: self.worker.open(
                    VisualWorkerOpen(
                        **operations.identity.model_dump(),
                        target_url=record.target_url,
                        allowed_origins=tuple(policy.allowed_origins),
                        deadline=deadline,
                        max_session_seconds=operations.step_timeout_seconds or min(
                            record.max_session_seconds, runtime.max_session_seconds
                        ),
                        step_timeout_seconds=operations.step_timeout_seconds,
                        max_states=max_states,
                        max_hops=max_hops,
                        max_screenshot_bytes=operations.max_frame_bytes,
                        interaction_scope=target_scope,
                        required_capabilities=(
                            (("dom-observation-v1", "viewport-context-v1", "target-preflight-v1")
                             if frozen_input else ())
                            + (("step-timeout-v1",) if step_timeout is not None else ())
                            + (("button-scope-v1", "anonymous-button-v1")
                               if target_scope in {"buttons", "visual_buttons"} else ())
                            + (("visual-button-scope-v1",)
                               if target_scope == "visual_buttons" else ())
                        ),
                    )
                )
            )
            sequence, proposal_sequence, visited = 0, 0, 0
            browser_parent = None
            active_page = None
            page_parents = {}
            page_revisions = {}
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
                binding=None,
                refresh_observation=False,
                history=None,
            ):
                nonlocal sequence, fingerprint, browser_parent, active_page
                live, _ = check_policy()
                if step_timeout is not None:
                    operations.step_timeout_seconds = min(step_timeout, live.max_session_seconds)
                operations.max_frame_bytes = min(
                    operations.max_frame_bytes, live.max_screenshot_bytes
                )
                sequence += 1
                command = VisualWorkerPrepare(
                    **operations.identity.model_dump(),
                    operation_id=uuid4(),
                    refresh_observation=refresh_observation,
                    purpose=purpose,
                    action=action,
                    expected_state_fingerprint=fingerprint,
                    state_id=state,
                    proposal_id=proposal,
                    checkpoint_id=checkpoint_id,
                    checkpoint_state_id=checkpoint_state_id,
                    restore_checkpoint_id=restore.id if restore else None,
                    history_checkpoint_id=history.id if history else None,
                    replay_operation_id=replay.operation.id if replay else None,
                    expected_locator=replay.locator.descriptor
                    if replay and replay.locator
                    else binding.expected_descriptor
                    if binding
                    else None,
                    dom_snapshot_id=binding.snapshot_id if binding else None,
                    dom_element_id=binding.element_id if binding else None,
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
                    checkpoint_id=restore.id if restore else history.id if history else None,
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
                await origins.capture()
                requests[operation.id], results[operation.id] = command, result
                fingerprint = result.state_fingerprint or fingerprint
                if result.operation.outcome_code == "step_timeout":
                    raise VisualOperationStopped("step_timeout")
                if result.operation.status == "unknown":
                    raise VisualOperationStopped("action_outcome_unknown")
                if result.operation.status == "completed":
                    before_page = result.operation.before_page_id
                    active_page = result.operation.after_page_id
                    if (action.kind in {"navigate", "back", "scroll", "type"}
                            or action.kind == "click" and active_page == before_page):
                        page_revisions[active_page] = page_revisions.get(active_page, 0) + 1
                    if action.kind == "click" and active_page != before_page:
                        page_parents[active_page] = before_page
                    if action.kind == "close_popup":
                        page_parents.pop(before_page, None)
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
            if (
                root.operation.status != "completed"
                or root.checkpoint is None
                or root.operation.actual_after_frame_id is None
            ):
                raise VisualOperationStopped("initial_capture_failed")
            visited = 1
            current = Branch(root_state, root.checkpoint, 0, (root.operation.id,), root)
            queue = []
            pages = []
            attempted = {}
            inventories = {}
            observations = {}
            observation_pages = {}
            observation_revisions = {}
            scroll_pending, scrolled = set(), set()
            stop_reason = None

            def save_inventory(branch, bound):
                page = inventory(branch.checkpoint, bound, attempted, target_scope)
                inventories[branch.state_id] = page
                self.uow.page_inventory(operations.lease, page)

            def mark_target(branch, binding, **status):
                if binding is None:
                    return
                key = target_key(branch.checkpoint, binding.expected_descriptor)
                attempted[key] = status
                # Update all retained observations of this URL, including a page
                # reached again through a self-link. IDs from old DOMs are not reused.
                for state_id, page in list(inventories.items()):
                    controls = tuple(control.model_copy(update=status)
                                     if page.url_fingerprint + ":" + control.key == key
                                     else control for control in page.controls)
                    if controls != page.controls:
                        updated = page.model_copy(update={"controls": controls})
                        inventories[state_id] = updated
                        self.uow.page_inventory(operations.lease, updated)
            effective = runtime.model_copy(
                update={
                    "max_steps": min(record.max_steps, runtime.max_steps),
                    "max_screenshot_bytes": operations.max_frame_bytes,
                }
            )
            guard = AgentStepGuard(policy_to_step_guard(effective))
            last_call = None
            codex = self.codex_candidates(lease) if frozen_input and self.codex_candidates else None
            codex_budget = (
                CodexCallBudget(
                    guard=guard,
                    max_calls=min(record.max_steps, runtime.max_steps),
                    max_rate=min(record.max_requests_per_minute, runtime.max_requests_per_minute),
                    deadline=deadline,
                    check_policy=lambda: check_policy()[0],
                )
                if frozen_input
                else None
            )

            async def refresh_page(branch):
                nonlocal visited
                # A read-only refresh records new evidence; it never repeats an
                # action. Reusing a DOM proposal additionally requires worker
                # verification of the original live targets against fresh evidence.
                state_id = uuid4()
                prior_ceiling = operations.deadline_ceiling
                source_page = active_page
                try:
                    for attempt in range(3):
                        _, latest = check_policy()
                        if (visited >= min(max_states, latest.vision_max_states)
                                or branch.hop >= min(max_hops, latest.vision_max_hops)):
                            raise VisualOperationStopped("exploration_coverage_incomplete")
                        refreshed = await primitive(
                            VisualWorkerAction(kind="wait", duration_ms=100), "setup",
                            state=branch.state_id, checkpoint_id=uuid4(),
                            checkpoint_state_id=state_id, refresh_observation=True,
                        )
                        if (attempt == 2 or active_page != source_page
                                or not can_reobserve_undispatched(
                                    refreshed, source_page, "wait", "setup",
                                )):
                            break
                        if attempt == 0:
                            ceiling = (refreshed.operation.started_at
                                       + timedelta(seconds=step_timeout)
                                       if step_timeout is not None else operations.deadline)
                            operations.deadline_ceiling = min(prior_ceiling, ceiling) \
                                if prior_ceiling else ceiling
                finally:
                    operations.deadline_ceiling = prior_ceiling
                if refreshed.operation.status != "completed" or not refreshed.checkpoint:
                    raise VisualOperationStopped(
                        (refreshed.operation.after_unavailable_reason or "capture_failed")
                        if refreshed.operation.status == "completed"
                        else refreshed.operation.outcome_code or "state_mismatch"
                    )
                visited += 1
                branch.state_id, branch.checkpoint = state_id, refreshed.checkpoint
                branch.hop += 1
                branch.path = (*branch.path, refreshed.operation.id)
                branch.result = refreshed

            async def scan_page(branch):
                live, _ = check_policy()
                for attempt in range(3):
                    try:
                        observed = await operations.bounded(
                            lambda live=live: self.worker.observe_dom(VisualWorkerObserveDom(
                                **operations.identity.model_dump(), snapshot_id=uuid4(),
                                expected_state_fingerprint=fingerprint,
                                max_elements=live.codex.max_dom_elements,
                                max_bytes=live.codex.max_dom_bytes,
                            )),
                        )
                        break
                    except VisionObservationUnavailable as error:
                        _, latest = check_policy()
                        if (error.code not in {"state_mismatch", "state_changed_during_observation"}
                                or attempt == 2
                                or visited >= min(max_states, latest.vision_max_states)
                                or branch.hop >= min(max_hops, latest.vision_max_hops)):
                            raise
                    # A fresh read is an explicit, recorded wait with new frame/state IDs.
                    # Existing screenshots, checkpoints and target bindings stay immutable.
                    await refresh_page(branch)
                bound = observed.data
                observations[branch.state_id] = bound
                observation_pages[branch.state_id] = active_page
                observation_revisions[branch.state_id] = page_revisions.get(active_page, 0)
                save_inventory(branch, bound)
                return bound

            async def refresh_scan_context(branch):
                previous = observations[branch.state_id]
                for attempt in range(3):
                    live, latest = check_policy()
                    checkpoint, matches = await operations.bounded(
                        lambda: self.worker.checkpoint(operations.identity, branch.checkpoint.id)
                    )
                    if checkpoint != branch.checkpoint:
                        raise VisualOperationStopped("state_mismatch")
                    if not matches:
                        if (branch.hop + 1 >= min(max_hops, latest.vision_max_hops)
                                or visited + len(queue) + 1 >= min(
                                    max_states, latest.vision_max_states,
                                )):
                            raise VisualOperationStopped("exploration_coverage_incomplete")
                        await refresh_page(branch)
                    try:
                        observed = await operations.bounded(
                            lambda live=live: self.worker.observe_dom(VisualWorkerObserveDom(
                                **operations.identity.model_dump(), snapshot_id=uuid4(),
                                expected_state_fingerprint=fingerprint,
                                max_elements=live.codex.max_dom_elements,
                                max_bytes=live.codex.max_dom_bytes,
                                revalidate_snapshot_id=previous.observation.snapshot_id,
                                revalidate_context_only=True,
                            )),
                        )
                    except VisionObservationUnavailable as error:
                        if attempt == 2 or error.code not in {
                            "state_mismatch", "state_changed_during_observation",
                        }:
                            raise
                        # Retry read-only evidence against the same original context.
                        # Every refresh consumes the existing state/hop/operation budget.
                        continue
                    observations[branch.state_id] = observed.data
                    observation_pages[branch.state_id] = active_page
                    observation_revisions[branch.state_id] = page_revisions.get(active_page, 0)
                    save_inventory(branch, observed.data)
                    return

            async def codex_propose(branch, remaining):
                if codex is None:
                    raise VisualOperationStopped("bridge_offline")
                if step_timeout is not None:
                    live, _ = check_policy()
                    operations.step_timeout_seconds = min(step_timeout, live.max_session_seconds)
                    codex_budget.deadline = datetime.now(UTC) + timedelta(
                        seconds=operations.step_timeout_seconds,
                    )
                # Acquire fresh evidence after rate waiting, not before a pause
                # that can span several carousel transitions.
                try:
                    await operations.bounded(codex_budget.wait_for_slot)
                except CodexUnavailable as error:
                    raise VisualOperationStopped(error.reason) from None
                bound = observations.get(branch.state_id)
                if (bound is None or observation_pages.get(branch.state_id) != active_page
                        or bound.observation.state_fingerprint != fingerprint):
                    bound = await scan_page(branch)
                bound = remaining_observation(branch.checkpoint, bound, attempted)
                if not bound.observation.elements:
                    return VisualCandidateBatchOutcome(status="completed", actions=[],
                                                       target_bindings=(), calls_used=0)

                async def check_state():
                    checkpoint, matches = await self.worker.checkpoint(
                        operations.identity,
                        branch.checkpoint.id,
                    )
                    return (
                        matches
                        and checkpoint == branch.checkpoint
                        and fingerprint == bound.observation.state_fingerprint
                    )

                async def capture_image():
                    # Use evidence captured with this checkpoint, not the preview's time cache.
                    frame_id = branch.result.operation.actual_after_frame_id
                    if frame_id is None:
                        raise VisualOperationStopped("capture_failed")
                    data = self.uow.read_frame(scope, frame_id)
                    return CodexImage(
                        data,
                        bound.observation.snapshot_id,
                        bound.observation.state_fingerprint,
                        sha256(data).hexdigest(),
                    )

                async def revalidate_targets(element_ids):
                    nonlocal bound
                    live, latest = check_policy()
                    if (branch.hop + 1 >= min(max_hops, latest.vision_max_hops)
                            or visited + len(queue) + 1 >= min(
                                max_states, latest.vision_max_states,
                            )):
                        return None
                    original_snapshot = bound.observation.snapshot_id
                    await refresh_page(branch)
                    try:
                        observed = await operations.bounded(
                            lambda: self.worker.observe_dom(VisualWorkerObserveDom(
                                **operations.identity.model_dump(), snapshot_id=uuid4(),
                                expected_state_fingerprint=fingerprint,
                                max_elements=live.codex.max_dom_elements,
                                max_bytes=live.codex.max_dom_bytes,
                                revalidate_snapshot_id=original_snapshot,
                                revalidate_element_ids=element_ids,
                            )),
                        )
                    except VisionObservationUnavailable as error:
                        self.uow.progress(
                            operations.lease, "candidate.revalidation_rejected",
                            f"candidate.revalidation_rejected:{branch.state_id}",
                            {"reason_code": error.code},
                        )
                        return None
                    bound = observed.data
                    observations[branch.state_id] = bound
                    observation_pages[branch.state_id] = active_page
                    observation_revisions[branch.state_id] = page_revisions.get(active_page, 0)
                    save_inventory(branch, bound)
                    self.uow.progress(
                        operations.lease, "candidate.revalidated",
                        f"candidate.revalidated:{branch.state_id}",
                        {"candidate_count": len(element_ids), "state_sequence": visited},
                    )
                    return bound

                return await operations.bounded(
                    lambda: codex.propose(
                        session=VisionModelSession(
                            record.tenant_id,
                            record.id,
                            record.provider,
                            record.model,
                            record.project_id,
                            record.correlation_id,
                            lease.fencing_token,
                        ),
                        bound=bound,
                        task_intent=intent,
                        observed_actions=tuple(
                            (results[item].operation.action_kind + " " +
                             (results[item].locator.descriptor.value
                              if results[item].locator else ""))[:120]
                            for item in results if results[item].operation.purpose == "explore"
                            and results[item].operation.status == "completed"
                        )[-10:],
                        max_candidates=min(10, remaining),
                        budget=codex_budget,
                        check_state=check_state,
                        capture_image=capture_image,
                        revalidate_targets=revalidate_targets,
                        deterministic_viewports=True,
                    )
                )

            async def propose(branch):
                nonlocal calls, last_call, proposal_sequence, model_failure, stop_reason
                live, latest = check_policy()
                if model_failure:
                    return
                if branch.hop >= min(max_hops, latest.vision_max_hops):
                    return
                remaining = min(max_states, latest.vision_max_states) - visited - len(queue)
                if remaining < 1:
                    return
                if calls >= min(record.max_steps, live.max_steps):
                    observed = observations.get(branch.state_id)
                    if (not frozen_input or observed is None or remaining_observation(
                        branch.checkpoint, observed, attempted,
                    ).observation.elements):
                        stop_reason = stop_reason or "exploration_call_limit"
                        return
                if frozen_input is None and last_call is not None:
                    interval = 60 / min(
                        record.max_requests_per_minute, live.max_requests_per_minute
                    )
                    wait = interval - (datetime.now(UTC) - last_call).total_seconds()
                    if wait > 0:
                        await operations.bounded(lambda: asyncio.sleep(wait))
                live, latest = check_policy()
                remaining = min(max_states, latest.vision_max_states) - visited - len(queue)
                if remaining < 1 or branch.hop >= min(max_hops, latest.vision_max_hops):
                    return
                self.uow.progress(
                    operations.lease,
                    "candidate.requested",
                    f"candidate.requested:{branch.state_id}",
                    {"state_sequence": visited, "hop": branch.hop},
                )
                if frozen_input is not None:
                    for refresh_attempt in range(3):
                        before_calls = codex_budget.calls
                        outcome = await codex_propose(branch, remaining)
                        live, latest = check_policy()
                        if (outcome.failure_reason != "bridge_stale_result"
                                or codex_budget.calls != before_calls
                                or outcome.calls_used != 0 or refresh_attempt == 2
                                or branch.hop + 1 >= min(max_hops, latest.vision_max_hops)
                                or visited + len(queue) + 1 >= min(
                                    max_states, latest.vision_max_states,
                                )):
                            break
                        # DOM can change after scan_page succeeds but before the
                        # first model reservation. Refresh only this pre-call race.
                        await refresh_page(branch)
                        remaining = min(max_states, latest.vision_max_states) - visited - len(queue)
                    calls = codex_budget.calls
                else:
                    frame_id = branch.result.operation.actual_after_frame_id
                    if frame_id is None:
                        raise VisualOperationStopped("capture_failed")
                    image = self.uow.read_frame(scope, frame_id)
                    if len(image) > min(record.max_screenshot_bytes, live.max_screenshot_bytes):
                        raise VisualOperationStopped("screenshot_byte_limit")
                    calls += 1
                    last_call = datetime.now(UTC)
                    outcome = await operations.bounded(
                        lambda: self.model_batch(
                            session=VisionModelSession(
                                record.tenant_id,
                                record.id,
                                record.provider,
                                record.model,
                            ),
                            screenshot=image,
                            task_intent=intent,
                            policy=live,
                            max_candidates=min(20, remaining),
                            guard=guard,
                            sequence=calls,
                            check_policy=check_policy,
                            remaining_seconds=min(step_timeout, live.max_session_seconds)
                            if step_timeout is not None else (
                                min(
                                    deadline,
                                    record.updated_at + timedelta(seconds=live.max_session_seconds),
                                )
                                - datetime.now(UTC)
                            ).total_seconds(),
                        )
                    )
                check_policy()
                await origins.capture()
                if outcome.viewport_scan_requested:
                    if not frozen_input or outcome.actions != []:
                        raise VisualOperationStopped("model_output_invalid")
                    # The model supplied no accepted action. Fresh private context
                    # gates the controller's existing deterministic scan instead.
                    await refresh_scan_context(branch)
                    self.uow.progress(
                        operations.lease, "viewport.scan_ready",
                        f"viewport.scan_ready:{branch.state_id}",
                        {"state_sequence": visited},
                    )
                if outcome.actions is None:
                    reason = vision_model_failure_reason(outcome.failure_reason)
                    if reason != "model_output_invalid":
                        raise VisualOperationStopped(reason)
                    # A malformed reply supplies no new actions. Previously validated
                    # siblings remain usable after normal checkpoint/locator checks.
                    # Do not retry the model or turn partial exploration into success.
                    model_failure = reason
                    self.uow.progress(
                        operations.lease,
                        "candidate.unavailable",
                        f"candidate.failed:{calls}",
                        {"reason_code": reason},
                    )
                    return
                self.uow.progress(
                    operations.lease,
                    "candidate.received",
                    f"candidate.received:{branch.state_id}",
                    {"state_sequence": visited, "candidate_count": len(outcome.actions)},
                )
                candidates = []
                bindings = outcome.target_bindings or (None,) * len(outcome.actions)
                if len(bindings) != len(outcome.actions):
                    raise VisualOperationStopped("model_output_invalid")
                pairs = list(zip(outcome.actions, bindings, strict=True))
                observed = observations.get(branch.state_id)
                if frozen_input and target_scope == "visual_buttons" and observed is not None:
                    elements = {e.element_id: e for e in observed.observation.elements}
                    if all(action.kind == "click" and binding is not None
                           and binding.snapshot_id == observed.observation.snapshot_id
                           and binding.element_id in elements
                           and binding.expected_descriptor.strategy == "dom_path"
                           and binding.expected_descriptor.schema_version == "v3"
                           for action, binding in pairs):
                        # These proposals are independent and already validated.
                        # Visit links before local UI changes can alter their href;
                        # deeper panel controls before shallower tab switches can
                        # hide them. Stable ties retain model order. No new target,
                        # binding, action or permission is introduced by scheduling.
                        pairs.sort(key=lambda item: (
                            elements[item[1].element_id].button_kind != "styled_link",
                            -item[1].expected_descriptor.value.count(" > "),
                        ))
                for action, binding in pairs:
                    if frozen_input and action.kind == "scroll":
                        # DOM viewport discovery belongs to the controller.
                        continue
                    if binding and target_key(branch.checkpoint, binding.expected_descriptor) in (
                        attempted
                    ):
                        continue
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
                    candidates.append((proposal_id, proposal_sequence, safe, edge, binding))
                    queue.append((branch, action, edge, binding))
                    mark_target(branch, binding, status="queued", proposal_id=proposal_id)
                self.uow.proposals(operations.lease, branch.state_id, candidates)
                if frozen_input:
                    page = inventories.get(branch.state_id)
                    if page and page.scrollable and page.state_id not in scrolled:
                        # Cover the next viewport before spending calls on child pages.
                        scroll_pending.add(branch.state_id)
                        pages.insert(0, branch)
                    elif page and candidates and any(
                        control.status == "pending" for control in page.controls
                    ):
                        pages.append(branch)

            async def restore(branch):
                nonlocal current, browser_parent
                # Restoration may switch tabs without creating a logical child.
                # Keep its live observation separate from queued branch evidence.
                cursor = replace(current)

                async def refresh_cursor():
                    _, latest = check_policy()
                    if (visited >= min(max_states, latest.vision_max_states)
                            or cursor.hop >= min(max_hops, latest.vision_max_hops)):
                        raise VisualOperationStopped("exploration_coverage_incomplete")
                    page_id = active_page
                    await refresh_page(cursor)
                    if active_page != page_id:
                        raise VisualOperationStopped("state_restore_failed")

                # Refresh/wait operations have identical before/after page IDs and
                # cannot tell us whether the current tab was originally a popup.
                # Keep the actual page ancestry independently of those operations.
                target_page = observation_pages.get(
                    branch.state_id, branch.result.operation.after_page_id,
                )
                while active_page != target_page and active_page in page_parents:
                    if cursor.result.operation.after_page_id != active_page:
                        await refresh_cursor()
                    # A destination popup can hydrate after its click evidence.
                    # Refresh that known child before closing it; never replace
                    # the source checkpoint or authorize a click from this read.
                    checkpoint, matches = await operations.bounded(
                        lambda: self.worker.checkpoint(operations.identity, cursor.checkpoint.id)
                    )
                    if checkpoint != cursor.checkpoint:
                        raise VisualOperationStopped("checkpoint_mismatch")
                    if not matches:
                        await refresh_cursor()
                    closed = await primitive(VisualWorkerAction(kind="close_popup"), "restore")
                    # A known child can hydrate between prepare and dispatch.
                    # Closing that same child is still the authorized restoration,
                    # but only positive proof of no dispatch permits a new attempt.
                    child_page, parent_page = active_page, page_parents.get(active_page)

                    def undispatched_close(result, child_page=child_page, parent_page=parent_page):
                        return can_refresh_undispatched_popup_close(result, child_page, parent_page)

                    if frozen_input and undispatched_close(closed):
                        prior_ceiling = operations.deadline_ceiling
                        ceiling = (closed.operation.started_at + timedelta(seconds=step_timeout)
                                   if step_timeout is not None else operations.deadline)
                        operations.deadline_ceiling = min(prior_ceiling, ceiling) \
                            if prior_ceiling else ceiling
                        try:
                            for _ in range(2):
                                await refresh_cursor()
                                if (active_page != child_page
                                        or page_parents.get(child_page) != parent_page):
                                    raise VisualOperationStopped("state_restore_failed")
                                closed = await primitive(
                                    VisualWorkerAction(kind="close_popup"), "restore",
                                )
                                if not undispatched_close(closed):
                                    break
                        finally:
                            operations.deadline_ceiling = prior_ceiling
                    if closed.operation.status != "completed":
                        raise VisualOperationStopped("state_restore_failed")
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
                if (frozen_input and not matches
                        and cursor.result.operation.after_page_id != active_page):
                    # A closed popup's URL/scroll says nothing about its opener.
                    # Capture the returned page before computing reversible scroll;
                    # the saved target checkpoint must still match independently.
                    await refresh_cursor()
                async def restore_scroll_if_needed(matches):
                    if (frozen_input and not matches and active_page == target_page
                            and cursor.checkpoint.url_fingerprint
                            == branch.checkpoint.url_fingerprint
                            and cursor.checkpoint.scroll_x == branch.checkpoint.scroll_x):
                        delta_y = branch.checkpoint.scroll_y - cursor.checkpoint.scroll_y
                        if delta_y and abs(delta_y) <= 100_000:
                            # Scroll only on the observed target Page/URL. The full
                            # immutable checkpoint, including forms, still gates actions.
                            while delta_y:
                                chunk = max(-2000, min(2000, delta_y))
                                moved = await primitive(
                                    VisualWorkerAction(kind="scroll", delta_y=chunk), "restore",
                                    state=branch.state_id,
                                )
                                if moved.operation.status != "completed":
                                    raise VisualOperationStopped(
                                        moved.operation.outcome_code or "state_restore_failed"
                                    )
                                delta_y -= chunk
                            _, matches = await operations.bounded(
                                lambda: self.worker.checkpoint(
                                    operations.identity, branch.checkpoint.id,
                                )
                            )
                    return matches

                matches = await restore_scroll_if_needed(matches)
                if frozen_input and not matches and branch.checkpoint.url_restore_allowed:
                    direct = await primitive(
                        VisualWorkerAction(kind="navigate"), "restore",
                        state=branch.state_id, restore=branch.checkpoint,
                    )
                    if direct.operation.status == "completed":
                        _, matches = await operations.bounded(
                            lambda: self.worker.checkpoint(
                                operations.identity, branch.checkpoint.id,
                            )
                        )
                        if matches:
                            current = branch
                            self.uow.progress(
                                operations.lease, "state.restored", f"restored:{sequence}"
                            )
                            return
                if not matches:
                    popup = active_page in page_parents
                    tentative = await primitive(
                        VisualWorkerAction(kind="close_popup" if popup else "back"), "restore",
                        history=branch.checkpoint if (frozen_input and not popup
                            and branch.result.history_restore_available) else None,
                    )
                    if tentative.operation.status == "unknown":
                        raise VisualOperationStopped("state_restore_failed")
                    _, matches = await operations.bounded(
                        lambda: self.worker.checkpoint(operations.identity, branch.checkpoint.id)
                    )
                    if (frozen_input and not popup
                            and tentative.operation.status == "completed"):
                        # History can change the URL before an SPA renders its
                        # destination. Refresh and reconcile reversible scroll;
                        # never repeat Back/click or substitute a new checkpoint.
                        for _ in range(2):
                            if matches and fingerprint == branch.result.state_fingerprint:
                                break
                            await refresh_cursor()
                            _, matches = await operations.bounded(
                                lambda: self.worker.checkpoint(
                                    operations.identity, branch.checkpoint.id,
                                )
                            )
                            # History restores its own viewport, which may differ
                            # from a queued sibling's checkpoint on that same page.
                            # Use the fresh returned cursor before considering replay.
                            matches = await restore_scroll_if_needed(matches)
                if matches:
                    verified = await primitive(
                        VisualWorkerAction(kind="wait", duration_ms=100),
                        "restore",
                        state=branch.state_id,
                        restore=branch.checkpoint,
                    )
                    # Only a proven, undispatched read-only verification can be
                    # observed again. Keep the rejection and original checkpoint;
                    # never repeat physical actions or reset the failed step's clock.
                    if frozen_input and can_reobserve_undispatched(
                        verified, active_page, "wait", "restore",
                    ):
                        prior_ceiling = operations.deadline_ceiling
                        recovery_ceiling = (
                            verified.operation.started_at + timedelta(seconds=step_timeout)
                            if step_timeout is not None else operations.deadline
                        )
                        operations.deadline_ceiling = min(
                            prior_ceiling, recovery_ceiling,
                        ) if prior_ceiling else recovery_ceiling
                        try:
                            for _ in range(2):
                                await refresh_cursor()
                                checkpoint, matches = await operations.bounded(
                                    lambda: self.worker.checkpoint(
                                        operations.identity, branch.checkpoint.id,
                                    )
                                )
                                if checkpoint != branch.checkpoint:
                                    raise VisualOperationStopped("checkpoint_mismatch")
                                if not matches:
                                    continue
                                verified = await primitive(
                                    VisualWorkerAction(kind="wait", duration_ms=100),
                                    "restore", state=branch.state_id, restore=branch.checkpoint,
                                )
                                if verified.operation.status == "completed":
                                    break
                                if not can_reobserve_undispatched(
                                    verified, active_page, "wait", "restore",
                                ):
                                    break
                        finally:
                            operations.deadline_ceiling = prior_ceiling
                else:
                    verified = None
                    # Validate the entire path before replaying even its prefix.
                    # A later non-replayable click must not cause a navigation or
                    # any earlier action to be repeated before the safe stop.
                    if any(not results[source_id].replayable for source_id in branch.path):
                        raise VisualOperationStopped("unsafe_replay")
                    for index, source_id in enumerate(branch.path):
                        source, command = results[source_id], requests[source_id]
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

            pinned_proposals = set()

            async def preflight_target(branch, edge, binding, *, restored=False):
                nonlocal current
                if (not frozen_input or target_scope != "visual_buttons" or binding is None
                        or binding.expected_descriptor.schema_version != "v3"):
                    return True
                checked = await operations.bounded(lambda: self.worker.check_target(
                    VisualWorkerCheckTarget(**operations.identity.model_dump(),
                        snapshot_id=binding.snapshot_id, element_id=binding.element_id,
                        checkpoint_id=branch.checkpoint.id, allow_restored_document=restored),
                ))
                if checked.matches_current:
                    if checked.same_document and not restored:
                        pinned_proposals.add(edge.proposal_id)
                    return True
                # A changed document, private form, origin or context cannot be
                # adopted. No operation exists and no physical retry is permitted.
                if not checked.context_matches:
                    self.uow.finish_edge(operations.lease, replace(
                        edge, status="terminal", outcome_code="stale_dom_context",
                    ))
                    raise VisualOperationStopped("stale_dom_context")
                stale = [(branch, None, edge, binding)] + [item for item in queue
                    if item[3] is not None
                    and observation_pages.get(item[0].state_id) == active_page
                    and item[0].checkpoint.url_fingerprint == branch.checkpoint.url_fingerprint]
                for source, _, old_edge, old_binding in stale:
                    key = target_key(source.checkpoint, old_binding.expected_descriptor)
                    previous = attempted.get(key, {})
                    if (previous.get("status") != "queued"
                            or previous.get("proposal_id") != old_edge.proposal_id
                            or previous.get("operation_id") is not None):
                        continue
                    self.uow.finish_edge(operations.lease, replace(
                        old_edge, status="terminal", outcome_code="stale_dom_context",
                    ))
                    queue[:] = [item for item in queue if item[2].id != old_edge.id]
                    mark_target(source, old_binding, status="pending",
                                proposal_id=None, operation_id=None)
                    attempted.pop(key)
                # Preserve original branch/checkpoint and audit. New evidence and
                # a new model proposal are required, within the existing budgets.
                fresh = Branch(current.state_id, current.checkpoint, current.hop,
                               current.path, current.result)
                await refresh_page(fresh)
                current = fresh
                await scan_page(fresh)
                pages[:] = [item for item in pages if item is not branch]
                pages.insert(0, fresh)
                self.uow.progress(operations.lease, "candidate.revalidation_rejected",
                    f"candidate.preflight:{edge.proposal_id}", {"reason_code": "stale_dom_context"})
                return False

            async def fresh_binding(branch, binding):
                if binding is None:
                    return None
                if (binding.expected_descriptor.strategy == "dom_path"
                        and binding.expected_descriptor.schema_version == "v2"):
                    # Preserve the original live-node token. A new DOM node at the
                    # same structural path must not inherit an older proposal.
                    return binding
                bound = observations.get(branch.state_id)
                if binding.expected_descriptor.schema_version == "v3":
                    # A child scan may already contain fresh bindings for this
                    # restored checkpoint. Reuse that observation only on the
                    # same page and since its last completed mutating action.
                    # The worker still verifies the retained exact node twice.
                    bound = next((observed for state_id, observed in reversed(
                        list(observations.items())
                    ) if observation_pages.get(state_id) == active_page
                        and observation_revisions.get(state_id)
                        == page_revisions.get(active_page, 0)
                        and observed.observation.state_fingerprint == fingerprint), None)
                if (bound is None or observation_pages.get(branch.state_id) != active_page
                        or bound.observation.state_fingerprint != fingerprint):
                    checkpoint = branch.checkpoint
                    bound = await scan_page(branch)
                    # Rebinding only preserves an already approved target on an
                    # equivalent restored checkpoint, never a changed page state.
                    if branch.checkpoint != checkpoint:
                        raise VisualOperationStopped("state_mismatch")
                matches = [item for item in bound.bindings
                           if item.descriptor == binding.expected_descriptor]
                if len(matches) != 1:
                    raise VisualOperationStopped("stale_dom_target")
                return binding.model_copy(update={
                    "snapshot_id": bound.observation.snapshot_id,
                    "observation_id": bound.observation.observation_id,
                    "state_fingerprint": bound.observation.state_fingerprint,
                    "element_id": matches[0].element_id,
                })

            # Inventory the source page before navigation can hide lower controls.
            # This baseline uses no LLM calls and is retained even if execution stops.
            source_url_fingerprint = root.checkpoint.url_fingerprint
            if frozen_input and target_scope == "visual_buttons":
                baseline = []
                while True:
                    await scan_page(current)
                    # An initially empty SPA can be stable before hydration.
                    # Give that first viewport bounded read-only observations;
                    # zero discovered controls cannot establish button coverage.
                    if not baseline:
                        for _ in range(2):
                            page = inventories[current.state_id]
                            if page.controls or page.scrollable:
                                break
                            _, latest = check_policy()
                            if (visited + 1 >= min(max_states, latest.vision_max_states)
                                    or current.hop + 1 >= min(max_hops, latest.vision_max_hops)):
                                break
                            await refresh_page(current)
                            await scan_page(current)
                        page = inventories[current.state_id]
                        if not page.controls and not page.scrollable:
                            raise VisualOperationStopped("exploration_coverage_incomplete")
                    baseline.append(current)
                    page = inventories[current.state_id]
                    if not page.scrollable:
                        break
                    _, latest = check_policy()
                    if (visited + 1 >= min(max_states, latest.vision_max_states)
                            or current.hop + 1 >= min(max_hops, latest.vision_max_hops)):
                        stop_reason = "exploration_coverage_incomplete"
                        break
                    state_id = uuid4()
                    moved = await primitive(
                        VisualWorkerAction(kind="scroll", delta_y=(
                            observations[current.state_id].next_scroll_delta_y or max(
                            100, int(observations[current.state_id].observation.viewport.height
                                     * .5),
                        ))), "setup", state=current.state_id,
                        checkpoint_id=uuid4(), checkpoint_state_id=state_id,
                    )
                    if moved.operation.status != "completed" or moved.checkpoint is None:
                        raise VisualOperationStopped(
                            (moved.operation.after_unavailable_reason or "capture_failed")
                            if moved.operation.status == "completed"
                            else moved.operation.outcome_code or "capture_failed"
                        )
                    if moved.checkpoint.scroll_y == current.checkpoint.scroll_y:
                        stop_reason = "exploration_coverage_incomplete"
                        break
                    scrolled.add(current.state_id)
                    visited += 1
                    current = Branch(state_id, moved.checkpoint, current.hop + 1,
                                     (*current.path, moved.operation.id), moved)
                self.uow.progress(operations.lease, "inventory.completed", "inventory.baseline", {
                    "state_sequence": visited,
                    "candidate_count": len({(p.url_fingerprint, c.key)
                                            for p in inventories.values() for c in p.controls}),
                })
                # Start at the live bottom viewport, then move upwards.
                pages.extend(reversed(baseline))
            else:
                await propose(current)
            while queue or pages:
                if target_scope == "visual_buttons":
                    pages[:] = [branch for branch in pages if (
                        (page := inventories.get(branch.state_id)) is None
                        or any(control.status == "pending" for control in page.controls)
                        or (page.scrollable and branch.state_id not in scrolled)
                    )]
                    if not queue and not pages:
                        break
                # A button may mutate local UI without a replayable URL. Explore
                # that live child before leaving it for siblings; returning later
                # would require replaying a potentially side-effecting click.
                live_child = (target_scope in {"buttons", "visual_buttons"} and any(
                    page is current for page in pages
                ) and any(not results[item].replayable for item in current.path)
                    and not any(item[0] is current for item in queue))
                if not queue or live_child:
                    index = next((i for i, page in enumerate(pages) if page is current), 0) \
                        if live_child else 0
                    branch = pages.pop(index)
                    live, latest = check_policy()
                    if (model_failure
                            or branch.hop >= min(max_hops, latest.vision_max_hops)
                            or visited >= min(max_states, latest.vision_max_states)):
                        stop_reason = stop_reason or "exploration_coverage_incomplete"
                        continue
                    scan_requested = branch.state_id in scroll_pending
                    scan_source_id = branch.state_id
                    if scan_requested and branch is current:
                        _, matches = await operations.bounded(
                            lambda branch=branch: self.worker.checkpoint(
                                operations.identity, branch.checkpoint.id,
                            )
                        )
                        if not matches:
                            await refresh_scan_context(branch)
                    else:
                        await restore(branch)
                    if scan_requested:
                        scroll_pending.discard(scan_source_id)
                        scroll_pending.discard(branch.state_id)
                        scrolled.add(scan_source_id)
                        scrolled.add(branch.state_id)
                        observed = observations[branch.state_id]
                        state_id = uuid4()
                        for attempt in range(3):
                            moved = await primitive(
                                VisualWorkerAction(kind="scroll", delta_y=max(
                                    100, int(observed.observation.viewport.height * 0.8),
                                )), "explore", state=branch.state_id,
                                checkpoint_id=uuid4(), checkpoint_state_id=state_id,
                            )
                            # A prepare/dispatch rejection performed no scroll.
                            # Revalidate fresh context before a new bounded intent;
                            # never retry an executed or unknown browser outcome.
                            if (moved.operation.status != "rejected" or attempt == 2
                                    or moved.operation.outcome_code not in {
                                        "state_mismatch", "state_changed_during_prepare",
                                    }):
                                break
                            await refresh_scan_context(branch)
                        scrolled.add(branch.state_id)
                        if moved.operation.status != "completed" or moved.checkpoint is None:
                            raise VisualOperationStopped(
                                (moved.operation.after_unavailable_reason or "capture_failed")
                                if moved.operation.status == "completed"
                                else moved.operation.outcome_code or "capture_or_action_failed"
                            )
                        if moved.checkpoint.scroll_y == branch.checkpoint.scroll_y:
                            stop_reason = stop_reason or "exploration_coverage_incomplete"
                            continue
                        visited += 1
                        branch = Branch(state_id, moved.checkpoint, branch.hop + 1,
                                        (*branch.path, moved.operation.id), moved)
                        current = branch
                        await scan_page(branch)
                    await propose(branch)
                    continue
                index = next((i for i, item in enumerate(queue) if item[0] is current), 0) \
                    if target_scope in {"buttons", "visual_buttons"} else 0
                branch, action, edge, binding = queue.pop(index)
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
                    same_view = (current is not None
                        and observation_pages.get(branch.state_id) == active_page
                        and current.checkpoint.url_fingerprint == branch.checkpoint.url_fingerprint
                        and current.checkpoint.scroll_x == branch.checkpoint.scroll_x
                        and current.checkpoint.scroll_y == branch.checkpoint.scroll_y)
                    if same_view and not await preflight_target(branch, edge, binding):
                        continue
                    await restore(branch)
                    if not same_view and not await preflight_target(
                        branch, edge, binding, restored=True,
                    ):
                        continue
                    restored_snapshot = binding.snapshot_id if binding else None
                    if edge.proposal_id not in pinned_proposals:
                        binding = await fresh_binding(branch, binding)
                    if (not same_view and frozen_input and target_scope == "visual_buttons"
                            and binding and binding.expected_descriptor.schema_version == "v3"):
                        # One verified restoration can recreate the whole document
                        # (including SPA nodes). Bind queued siblings now, while
                        # that restoration is proven, instead of granting a future
                        # same-URL reload permission to inherit the old proposals.
                        for index, item in enumerate(queue):
                            source, command, queued_edge, queued_binding = item
                            if (queued_binding is None
                                    or queued_binding.snapshot_id != restored_snapshot):
                                continue
                            check = VisualWorkerCheckTarget(**operations.identity.model_dump(),
                                snapshot_id=queued_binding.snapshot_id,
                                element_id=queued_binding.element_id,
                                checkpoint_id=source.checkpoint.id,
                                allow_restored_document=True)
                            checked = await operations.bounded(
                                lambda check=check: self.worker.check_target(check),
                            )
                            if checked.matches_current:
                                queue[index] = (source, command, queued_edge,
                                                await fresh_binding(source, queued_binding))
                    pinned_proposals.discard(edge.proposal_id)
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
                    binding=binding,
                    checkpoint_id=uuid4(),
                    checkpoint_state_id=child_id,
                )
                mark_target(branch, binding, status=result.operation.status,
                            proposal_id=edge.proposal_id, operation_id=result.operation.id)
                if result.operation.status == "rejected":
                    continue
                if result.operation.status != "completed" or result.checkpoint is None:
                    raise VisualOperationStopped(
                        (result.operation.after_unavailable_reason or "capture_failed")
                        if result.operation.status == "completed"
                        else result.operation.outcome_code or "capture_or_action_failed"
                    )
                visited += 1
                current = Branch(
                    child_id,
                    result.checkpoint,
                    branch.hop + 1,
                    (*branch.path, result.operation.id),
                    result,
                )
                if (frozen_input and target_scope == "visual_buttons"
                        and action.kind == "click" and not result.replayable
                        and result.operation.before_page_id == result.operation.after_page_id
                        and current.checkpoint.url_fingerprint == branch.checkpoint.url_fingerprint
                        and current.checkpoint.scroll_x == branch.checkpoint.scroll_x
                        and current.checkpoint.scroll_y == branch.checkpoint.scroll_y
                        and result.state_fingerprint != branch.result.state_fingerprint):
                    # A local UI mutation makes cached siblings refer to an old
                    # checkpoint. Retain their terminal audit records, release only
                    # never-dispatched targets, and ask the model again on fresh
                    # child evidence. Never replay the mutation or migrate a live
                    # binding/proposal to a different state.
                    for queued in list(queue):
                        source, _, old_edge, old_binding = queued
                        if (old_binding is None
                                or observation_pages.get(source.state_id) != active_page
                                or source.checkpoint.url_fingerprint
                                != current.checkpoint.url_fingerprint):
                            continue
                        key = target_key(source.checkpoint, old_binding.expected_descriptor)
                        previous = attempted.get(key, {})
                        if (previous.get("status") != "queued"
                                or previous.get("proposal_id") != old_edge.proposal_id
                                or previous.get("operation_id") is not None):
                            continue
                        self.uow.finish_edge(operations.lease, replace(
                            old_edge, status="terminal", outcome_code="stale_dom_context",
                        ))
                        queue.remove(queued)
                        mark_target(source, old_binding, status="pending",
                                    proposal_id=None, operation_id=None)
                        attempted.pop(key)
                    pages[:] = [page for page in pages if page is not branch]
                if (target_scope == "visual_buttons"
                        and current.checkpoint.url_fingerprint != source_url_fingerprint):
                    continue
                if frozen_input:
                    previous = observations.get(branch.state_id)
                    if (target_scope == "visual_buttons" and action.kind == "click"
                            and previous is not None
                            and result.operation.before_page_id == result.operation.after_page_id
                            and result.semantic_change == "unchanged"
                            and result.checkpoint.semantic_fingerprint
                            == branch.checkpoint.semantic_fingerprint
                            and result.state_fingerprint == branch.result.state_fingerprint
                            and previous.observation.state_fingerprint == result.state_fingerprint):
                        # Keep the original live-node bindings after a fully unchanged
                        # observation. A later replacement must fail exact-node checks,
                        # never inherit an already approved sibling proposal. The new
                        # result state and both operation frames are still retained.
                        observations[current.state_id] = previous
                        observation_pages[current.state_id] = active_page
                        observation_revisions[current.state_id] = page_revisions.get(active_page, 0)
                        save_inventory(current, previous)
                    else:
                        await scan_page(current)
                    if (target_scope == "visual_buttons" and branch.state_id in scrolled
                            and result.state_fingerprint == branch.result.state_fingerprint):
                        scrolled.add(current.state_id)
                    if (action.kind == "scroll"
                            and current.checkpoint.scroll_y > branch.checkpoint.scroll_y):
                        scrolled.add(branch.state_id)
                        scroll_pending.discard(branch.state_id)
                        pages[:] = [page for page in pages if page is not branch]
                # Finish the cached sibling batch before spending another model call
                # on a child page. Previously each click interrupted its siblings.
                if frozen_input:
                    pages.append(current)
                else:
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
            await origins.capture()
            if frozen_input and model_failure is None:
                partial = any(
                    page.truncated or page.skipped_count
                    or (page.scrollable and page.state_id not in scrolled)
                    or any(control.status != "completed" for control in page.controls)
                    for page in inventories.values()
                )
                if partial:
                    model_failure = stop_reason or "exploration_coverage_incomplete"
            return self.uow.finish(
                operations.lease,
                model_failure,
                handoff=handoff,
                intent=intent,
                handoff_reason=handoff_reason,
            )
        except Exception as error:
            if opened:
                await origins.capture()
            reason = (
                "image_delivery_auth_required"
                if isinstance(error, VisionImageAuthorizationRequired)
                else str(error)
                if isinstance(error, (VisualOperationStopped, VisionObservationUnavailable))
                else ("step_timeout" if step_timeout is not None else "session_timeout")
                if isinstance(error, TimeoutError)
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
