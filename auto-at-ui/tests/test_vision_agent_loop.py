"""Agent-loop processor against a fake worker (applying the budget formula) and a fake exchange."""

import asyncio
import importlib.util
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from agents.prompts.agent_loop import build_prompt
from agents.shared.runtime import AGENT_RUNTIME_CONFIG_KEY
from application.vision_agent_loop import (
    MIN_OPERATION_BUDGET,
    REFRESH_ATTEMPTS,
    VisionAgentLoopProcessor,
    allowed_hosts,
    render_snapshot,
    resolve_ref,
    worker_operation_budget,
)
from application.vision_results import VisionResults
from auto_at.contracts.codex_bridge import (
    AGENT_HISTORY_ITEM_MAX_CHARS,
    AGENT_HISTORY_MAX_ITEMS,
    AGENT_MEMORY_MAX_CHARS,
    AGENT_REQUEST_MAX_BYTES,
    AgentAction,
    AgentLoopContext,
    AgentStep,
    CodexBoundObservation,
    CodexBridgeRequest,
    CodexConsentSnapshot,
    CodexDomElement,
    CodexDomObservation,
    CodexElementBinding,
    CodexNeedScreenshot,
    CodexStop,
    content_hash,
)
from auto_at.contracts.vision import (
    VisualCheckpoint,
    VisualLocatorDescriptor,
    VisualLocatorEvidence,
)
from auto_at.contracts.vision_worker import (
    VisualWorkerDomObservation,
    VisualWorkerOperationResult,
    VisualWorkerOriginObservations,
)
from config import Settings
from domain.authorization import Principal, Role
from domain.codex_bridge import input_snapshot
from domain.runs import OutboxEvent
from domain.vision import VisionObservationUnavailable, VisualSessionScope
from domain.vision_agent_safety import BLOCKED_ACTION_TERMS
from infrastructure.persistence.models import (
    Base,
    ProjectExecutionPolicyModel,
    ProjectModel,
    VisualAgentStepModel,
    VisualExplorationSessionModel,
)
from infrastructure.persistence.repositories import (
    SqlAlchemyAuditEventRepository,
    SqlAlchemyConfigurationRepository,
    SqlAlchemyVisionRepository,
    SqlAlchemyVisualTraceRepository,
)
from infrastructure.persistence.vision_unit_of_work import SqlAlchemyVisualTraceUnitOfWork
from sqlalchemy import update
from sqlalchemy.orm import sessionmaker
from test_codex_candidate_service import codex_policy
from vision_trace_fixtures import MemoryFrameStore, evolve, frame, session_values

pytest_plugins = ["vision_trace_fixtures"]
PNG = b"\x89PNG\r\n\x1a\nfixture"
APP = "https://app.test/"
SHA = "a" * 64


def sha(label):
    import hashlib

    return hashlib.sha256(label.encode()).hexdigest()


# --------------------------------------------------------------------------- renderer / refs

def dom_element(index, name, **overrides):
    return CodexDomElement.model_validate({
        "element_id": f"e_{index:032x}", "role": "button", "name": name, "enabled": True,
        "editable": False, **overrides,
    })


def bound_for(elements, *, skipped=0, request=None):
    ids = dict(tenant_id="t", project_id=uuid4(), session_id=uuid4(), fencing_token=1)
    if request is not None:
        ids = dict(tenant_id=request.tenant_id, project_id=request.project_id,
                   session_id=request.session_id, fencing_token=request.fencing_token)
    observation = CodexDomObservation(
        **ids, observation_id=uuid4(),
        snapshot_id=request.snapshot_id if request else uuid4(), state_fingerprint=SHA,
        captured_at=datetime.now(UTC), viewport={"width": 1280, "height": 720},
        elements=tuple(elements), skipped_count=skipped,
    )
    bindings = tuple(CodexElementBinding(
        element_id=item.element_id,
        descriptor=VisualLocatorDescriptor(
            strategy="role", role=item.role, value=item.name or "unnamed"),
        bounds={"x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
    ) for item in elements)
    return CodexBoundObservation(observation=observation, bindings=bindings)


def long_names(count=100):
    return [dom_element(i, f"N{i:03d} " + "x" * 114) for i in range(1, count + 1)]


def test_renderer_trims_to_the_cap_with_an_exact_marker_and_reports_skipped_controls():
    bound = bound_for(long_names(), skipped=200)
    rendered = render_snapshot(bound, 7, 4000, "https://app.test/page")
    assert len(rendered.text) <= 4000
    assert "200 control ngoài snapshot" in rendered.text
    marker = re.search(r"\[refs (\d+:\d+)-(\d+:\d+) trimmed\]", rendered.text)
    first, last = marker.groups()
    shown = len(rendered.refs)
    assert 0 < shown < 100
    assert first == f"7:{shown + 1}" and last == "7:100"
    assert set(rendered.refs) == {f"7:{n}" for n in range(1, shown + 1)}
    lines = rendered.text.splitlines()
    assert sum(line.startswith("7:") and " button " in line for line in lines) == shown
    assert rendered.trimmed == (first, last)


def test_renderer_keeps_everything_that_fits_without_a_marker():
    bound = bound_for([dom_element(1, "Open"), dom_element(2, "Close")])
    rendered = render_snapshot(bound, 2, 4000)
    assert "trimmed" not in rendered.text and "ngoài snapshot" not in rendered.text
    assert list(rendered.refs) == ["2:1", "2:2"] and rendered.trimmed is None
    assert '2:1 button "Open"' in rendered.text


def test_renderer_quotes_names_so_page_text_cannot_forge_lines_or_refs():
    rendered = render_snapshot(bound_for([dom_element(1, '3:9 button "x"')]), 3, 4000)
    assert len([line for line in rendered.text.splitlines() if line.startswith("3:")]) == 1


@pytest.mark.parametrize("ref", ["", "abc", "3", "3:", ":4", "1:2:3", "-1:2", "3:x", "3: 4"])
def test_refs_with_the_wrong_shape_are_invalid_not_stale(ref):
    assert resolve_ref(ref, 3, {"3:1": object()}) == (None, "invalid_ref")


@pytest.mark.parametrize("ref", ["2:1", "4:1", "3:99", "03:1", "3:01"])
def test_old_future_unknown_or_not_shown_refs_are_stale(ref):
    assert resolve_ref(ref, 3, {"3:1": object()}) == (None, "stale_ref")


def test_a_ref_in_the_current_map_resolves():
    marker = object()
    assert resolve_ref("3:1", 3, {"3:1": marker}) == (marker, None)


def test_allowed_hosts_are_bounded_and_the_worst_prompt_fits_the_request_cap():
    origins = [f"https://{'h' * 40}{i}.example.test" for i in range(60)]
    assert len(allowed_hosts(origins)) == 20 and allowed_hosts(["*"]) == ("*",)
    worst = bound_for([dom_element(1, "Mở")])
    policy = codex_policy(raw_screenshot_transfer_accepted=False)
    consent = CodexConsentSnapshot(**policy.codex.model_dump())
    context = AgentLoopContext(
        task="Đ" * 4000, allowed_hosts=tuple(("a" * 250 + str(i))[:255] for i in range(20)),
        memory="ệ" * AGENT_MEMORY_MAX_CHARS,
        history=("ệ" * AGENT_HISTORY_ITEM_MAX_CHARS,) * AGENT_HISTORY_MAX_ITEMS,
        snapshot_version=1_000_000, snapshot="ệ" * 24_000,
    )
    obs = worst.observation
    request = CodexBridgeRequest(
        tenant_id=obs.tenant_id, project_id=obs.project_id, session_id=obs.session_id,
        fencing_token=1, observation_id=obs.observation_id, snapshot_id=obs.snapshot_id,
        state_fingerprint=SHA, job_id=uuid4(), bridge_id=uuid4(), correlation_id=uuid4(),
        request_sequence=1, prompt_version="agent-loop-v2", stage="dom",
        created_at=datetime.now(UTC), deadline=datetime.now(UTC) + timedelta(seconds=60),
        consent=consent, consent_hash=content_hash(consent),
        inputs=dict(dom_sha256=SHA, dom_bytes=100, schema_sha256=SHA, schema_bytes=100),
        candidate_limit=10, agent_context=context,
    )
    assert len(build_prompt(request, b"")) <= AGENT_REQUEST_MAX_BYTES


def test_worker_budget_formula_for_the_chosen_limits_covers_twenty_calls_of_ten_actions():
    assert MIN_OPERATION_BUDGET == 401
    assert worker_operation_budget() >= MIN_OPERATION_BUDGET


# --------------------------------------------------------------------------- fakes

@dataclass
class Outcome:
    status: str = "completed"
    code: str = "observed"
    url_change: str = "unchanged"
    fingerprint: str | None = None
    popup: bool = False
    page_url: str | None = None


class FakeWorker:
    """Applies the real worker's operation budget formula and records every request."""

    def __init__(self, uow, scope, *, page_url=APP, elements=None, plan=None):
        self.uow, self.scope, self.page_url = uow, scope, page_url
        self.plan = plan or (lambda request, n: Outcome())
        self.fingerprint, self.page_id = sha("f0"), uuid4()
        self.elements = elements or [
            ("button", "Details", None, True, False),
            ("textbox", "Name", "text", True, True),
            ("textbox", "Nickname", "text", True, True),
            ("button", "Delete account", None, True, False),
            ("button", "Send", "submit", True, False),
            ("button", "ĐĂNG KÝ", None, True, False),
            ("button", "Reset", "reset", True, False),
        ]
        self.calls, self.prepares, self.observes, self.requests = [], [], [], {}
        self.results, self.operations, self.open_request, self.observe_errors = {}, 0, None, []
        self.closed = False
        self.ancestry, self.latest_snapshot = [], None
        # Redirect race: `session.state` is stale once a click lands, so the next read mismatches.
        self.errors_after_click = []

    @staticmethod
    def _reject(code):
        raise RuntimeError(code)

    async def open(self, request):
        self.calls.append("open")
        # The real worker's rule (workers/playwright/src/vision-operations.ts open()).
        now = datetime.now(UTC)
        if not (now < request.deadline <= now + timedelta(seconds=request.max_session_seconds)):
            raise RuntimeError("invalid_deadline")
        self.open_request = request
        return self.fingerprint

    async def observe_dom(self, request):
        self.calls.append("observe_dom")
        self.observes.append(request)
        self.latest_snapshot = request.snapshot_id
        if self.observe_errors:
            raise VisionObservationUnavailable(self.observe_errors.pop(0))
        if request.expected_state_fingerprint != self.fingerprint:
            raise VisionObservationUnavailable("state_mismatch")
        elements = [dom_element(i, name, role=role, input_type=kind, enabled=enabled,
                                editable=editable)
                    for i, (role, name, kind, enabled, editable) in enumerate(self.elements, 1)]
        bound = bound_for(elements, request=request)
        observation = bound.observation.model_copy(update={"state_fingerprint": self.fingerprint})
        return VisualWorkerDomObservation(
            tenant_id=request.tenant_id, project_id=request.project_id,
            session_id=request.session_id, fencing_token=request.fencing_token,
            data=bound.model_copy(update={"observation": observation}),
        )

    async def origins(self, identity):
        return VisualWorkerOriginObservations(
            tenant_id=identity.tenant_id, project_id=identity.project_id,
            session_id=identity.session_id, fencing_token=identity.fencing_token,
            items=(), truncated=False,
        )

    def _intent(self, operation_id):
        return next(op for op in self.uow.read_snapshot(self.scope)["operations"]
                    if op.id == operation_id)

    def _result(self, operation, frames, **fields):
        return VisualWorkerOperationResult(
            operation=operation, frames=tuple(frames), locator=fields.pop("locator", None),
            prepared_handle=uuid4(), state_fingerprint=fields.pop("fingerprint", self.fingerprint),
            checkpoint=fields.pop("checkpoint", None),
            semantic_change="changed", duration_ms=1, acknowledged=False, replayable=False,
            **fields,
        )

    async def prepare(self, request):
        self.calls.append("prepare")
        self.prepares.append(request)
        # Worker rule for `prepare`: a step deadline exactly when the session is in step mode.
        step = self.open_request.step_timeout_seconds
        if step is None:
            assert request.step_deadline is None, "invalid_step_deadline"
        else:
            now = datetime.now(UTC)
            limit = now + timedelta(seconds=step)
            assert request.step_deadline is not None, "invalid_step_deadline"
            assert now < request.step_deadline <= limit, "invalid_step_deadline"
        self.requests[request.operation_id] = request
        intent = self._intent(request.operation_id)
        # Like the real worker, a failed rule is a rejected operation result, not a transport error.
        try:
            self._worker_rules(request)
            rule = None
        except RuntimeError as error:
            rule = str(error)
        self.operations += 1
        budget = worker_operation_budget(self.open_request.max_states, self.open_request.max_hops)
        ordinal = len(self.prepares) - 1
        outcome = Outcome("rejected", rule) if rule else self.plan(request, ordinal)
        if self.operations > budget:
            outcome = Outcome("rejected", "operation_budget_exhausted")
        if outcome.status == "rejected":
            rejected = evolve(
                intent, status="rejected", ended_at=datetime.now(UTC),
                outcome_code=outcome.code, before_unavailable_reason="action_not_executed",
                after_unavailable_reason="action_not_executed",
            )
            result = self._result(rejected, (), dispatch_started=False, failure_stage="prepare")
            self.results[intent.id] = result
            return result
        before = frame(intent, "before", PNG)
        locator = None
        if request.action.kind in {"click", "type"}:
            assert request.dom_snapshot_id and request.dom_element_id and request.expected_locator
            locator = VisualLocatorEvidence(
                id=uuid4(), tenant_id=intent.tenant_id, project_id=intent.project_id,
                session_id=intent.session_id, operation_id=intent.id, state_id=intent.state_id,
                proposal_id=intent.proposal_id, originating_frame_id=before.metadata.id,
                descriptor=request.expected_locator,
                bounding_box={"x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
                matched_count=1, target_match=True, actionable=True, model_confidence=0,
                verified_at=datetime.now(UTC), status="verified",
            )
        # parent_operation_id is the worker's, not an echo (vision-operations.ts:502).
        parent = None if request.action.kind == "navigate" else (
            self.ancestry[-1] if self.ancestry else None)
        prepared = evolve(
            intent, actual_before_frame_id=before.metadata.id, before_page_id=self.page_id,
            parent_operation_id=parent,
            locator_id=locator.id if locator else None,
        )
        result = self._result(prepared, (before.metadata,), locator=locator)
        self.results[intent.id] = result
        return result

    def _worker_rules(self, request):
        """Checks the real worker applies in `prepare` (vision-operations.ts:488-585)."""
        if self.ancestry and not self.page_url.startswith("https://app.test"):
            # K3, worker rule (vision-operations.ts): leaving the page, or the read-only refresh.
            refresh = (request.refresh_observation and request.purpose == "setup"
                       and request.action.kind == "wait")
            if request.action.kind not in {"close_popup", "back"} and not refresh:
                self._reject("origin_blocked")
        if request.refresh_observation:
            if not (request.purpose == "setup" and request.action.kind == "wait"
                    and request.checkpoint_id and not request.proposal_id
                    and not request.dom_snapshot_id and not request.expected_locator):
                self._reject("invalid_observation_refresh")
        if request.expected_state_fingerprint != self.fingerprint:
            self._reject("state_mismatch")
        if request.dom_snapshot_id and request.dom_snapshot_id != self.latest_snapshot:
            self._reject("stale_dom_snapshot")
        sequential = request.purpose == "explore"
        if request.action.kind == "navigate" and not (request.purpose == "setup" or sequential):
            self._reject("invalid_navigation_purpose")
        if request.action.kind in {"back", "close_popup"} and not sequential:
            self._reject("invalid_restore_purpose")
        if request.action.kind == "type" and "\n" in (request.action.text or ""):
            self._reject("sensitive_action_blocked")

    async def execute(self, command):
        self.calls.append("execute")
        prior = self.results[command.operation_id]
        request = self.requests[command.operation_id]
        outcome = self.plan(request, len(self.prepares) - 1)
        outcome = outcome if outcome.status != "rejected" else Outcome()
        before = prior.frames[0]
        after_page = uuid4() if outcome.popup else self.page_id
        if outcome.fingerprint:
            self.fingerprint = outcome.fingerprint
        if outcome.page_url:
            self.page_url = outcome.page_url
        if request.action.kind == "click" and outcome.status == "completed":
            self.observe_errors = list(self.errors_after_click)
        changes = dict(
            status=outcome.status, ended_at=datetime.now(UTC), outcome_code=outcome.code,
            after_page_id=after_page, url_change=outcome.url_change, visual_change="changed",
        )
        frames = [before]
        if outcome.status == "unknown":
            changes["after_unavailable_reason"] = "capture_failed"
        else:
            after = frame(prior.operation, "after", PNG)
            changes["actual_after_frame_id"] = after.metadata.id
            frames.append(after.metadata)
        final = evolve(prior.operation, **changes)
        checkpoint = None
        if request.checkpoint_id and outcome.status == "completed":
            checkpoint = VisualCheckpoint(
                id=request.checkpoint_id, state_id=request.checkpoint_state_id,
                url_fingerprint=sha(self.page_url), semantic_fingerprint=sha(self.fingerprint),
                scroll_x=0, scroll_y=0, page_url=self.page_url,
            )
        if outcome.popup:
            self.page_id = after_page
        if outcome.status == "completed":
            # Worker ancestry: setup navigate resets, setup refresh/scroll push, explore never.
            if request.action.kind == "navigate" and request.purpose == "setup":
                self.ancestry = [request.operation_id]
            elif request.purpose == "setup" and (
                    request.refresh_observation or request.action.kind == "scroll"):
                self.ancestry.append(request.operation_id)
        result = self._result(final, frames, locator=prior.locator, checkpoint=checkpoint,
                              fingerprint=self.fingerprint)
        self.results[command.operation_id] = result
        return result

    async def read(self, identity, operation_id):
        return self.results[operation_id]

    async def frame(self, identity, metadata):
        return PNG

    async def acknowledge(self, request):
        return self.results[request.operation_id]

    async def close(self, identity):
        self.closed = True

    def explore_kinds(self):
        return [p.action.kind for p in self.prepares if p.purpose == "explore"]


class FakeExchange:
    def __init__(self, outputs, on_call=None):
        self.outputs, self.calls, self.on_call = list(outputs), [], on_call

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.on_call:
            self.on_call(len(self.calls))
        item = self.outputs[len(self.calls) - 1] if len(self.calls) <= len(self.outputs) else None
        if item is None:
            item = self.outputs[-1]
        if callable(item):
            item = item(kwargs)
        if isinstance(item, str):
            return SimpleNamespace(output=None, failure_code=item, job_id=uuid4())
        return SimpleNamespace(output=item, failure_code=None, job_id=uuid4())


def click(ref):
    return AgentAction(kind="click", ref=ref)


def typed(ref, text="abc"):
    return AgentAction(kind="type", ref=ref, text=text)


def wait():
    return AgentAction(kind="wait", duration_ms=100)


def step(*actions, memory="remember", goal="goal"):
    return AgentStep(evaluation_previous_goal="eval", memory=memory, next_goal=goal,
                     actions=tuple(actions))


DONE = CodexStop(reason="complete")


class Session:
    """One seeded session plus the objects a test needs to inspect it."""


def seed(engine, *, policy=None, state="queued", **overrides):
    policy = policy or codex_policy(max_steps=20, max_requests_per_minute=10_000)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    scope = VisualSessionScope("tenant-codex", uuid4(), uuid4())
    with factory.begin() as db:
        db.add(ProjectModel(id=scope.project_id, tenant_id=scope.tenant_id, name="Agent",
                            default_target="web_ui"))
        db.flush()
        db.add(VisualExplorationSessionModel(**session_values(
            scope, state=state, trace_version="v4", provider="codex_cli", model="gpt-6-luna",
            model_input_policy=input_snapshot(policy).model_dump(mode="json"),
            target_url=APP, max_steps=policy.max_steps, max_requests_per_minute=10_000,
            max_screenshot_bytes=1_000_000, max_session_seconds=60,
            exploration_engine="agent_loop", **overrides,
        )))
        db.add(ProjectExecutionPolicyModel(
            project_id=scope.project_id, tenant_id=scope.tenant_id,
            allowed_origins=["https://app.test"], vision_max_hops=5, vision_max_states=5,
        ))
        SqlAlchemyConfigurationRepository(db).set(
            scope.tenant_id, AGENT_RUNTIME_CONFIG_KEY, {"vision": policy.model_dump(mode="json")})
    store = MemoryFrameStore()
    uow = SqlAlchemyVisualTraceUnitOfWork(factory, store)
    out = Session()
    out.factory, out.scope, out.uow, out.store, out.policy = factory, scope, uow, store, policy
    return out


def run_agent(disposable_database, monkeypatch, outputs, *, worker=None, exchange=None,
              policy=None, chars=24_000, state="queued", clock=None, now=None, on_seed=None,
              **overrides):
    monkeypatch.setattr("application.vision_agent_loop.decrypt_visual_intent",
                        lambda *_: "Click every harmless control")
    seeded = seed(disposable_database, policy=policy, state=state, **overrides)
    if on_seed:
        on_seed(seeded)
    seeded.worker = worker or FakeWorker(seeded.uow, seeded.scope)
    seeded.worker.uow, seeded.worker.scope = seeded.uow, seeded.scope
    seeded.exchange = exchange or FakeExchange(outputs)
    settings = Settings(_env_file=None, vision_worker_secret="fixture-only",
                        vision_agent_snapshot_chars=chars)
    kwargs = {}
    if clock:
        kwargs.update(clock=clock[0], sleep=clock[1])
    if now:
        kwargs["now"] = now
    seeded.processor = VisionAgentLoopProcessor(
        seeded.uow, seeded.worker, settings, lambda lease: seeded.exchange, **kwargs)
    seeded.event = OutboxEvent(
        id=uuid4(), tenant_id=seeded.scope.tenant_id,
        event_type="agent.visual_exploration.requested.v1", schema_version="v1",
        correlation_id=uuid4(), causation_id=None, idempotency_key="agent-loop",
        payload={"session_id": str(seeded.scope.session_id)})
    seeded.error = None
    try:
        seeded.outcome = asyncio.run(seeded.processor.execute(seeded.event))
    except Exception as error:
        seeded.error = error
    seeded.record = seeded.uow.get_session(seeded.scope.tenant_id, seeded.scope.session_id)
    seeded.steps = seeded.uow.agent_steps(seeded.scope)
    seeded.operations = seeded.uow.read_snapshot(seeded.scope)["operations"]
    return seeded


# --------------------------------------------------------------------------- loop behaviour

def test_three_steps_reach_agent_done_with_a_complete_step_log(disposable_database, monkeypatch):
    outputs = [
        step(click("1:1"), typed("1:2"), click("1:4"), click("1:5"), click("1:7"),
             click("1:6")),
        step(click("1:1"), click("2:99"), click("zzz"), wait()),
        DONE,
    ]
    run = run_agent(disposable_database, monkeypatch, outputs)
    assert run.error is None and run.record.safe_failure_reason == "agent_done"
    assert [s.step_index for s in run.steps] == [1, 2, 3]
    first = run.steps[0]
    assert (first.evaluation_previous_goal, first.memory, first.next_goal) == (
        "eval", "remember", "goal")
    reasons = [a.get("skipped_reason") for a in first.actions]
    assert reasons == [None, None, "sensitive_action_blocked", "sensitive_action_blocked",
                       "sensitive_action_blocked", None]
    assert first.actions[5]["ref"] == "1:6"  # "ĐĂNG KÝ" must not be blocked
    assert len(first.operation_ids) == 3 <= len(first.actions)
    ran = {a["result"]["operation_id"] for a in first.actions if "result" in a}
    assert ran == set(first.operation_ids)
    assert all(("result" in a) != ("skipped_reason" in a) for s in run.steps for a in s.actions)
    second = run.steps[1]
    assert [a.get("skipped_reason") for a in second.actions] == ["stale_ref", "stale_ref",
                                                                  "invalid_ref", None]
    assert run.steps[2].actions == [] and run.steps[2].stop_reason == "agent_done"
    # Only the newest snapshot reaches the model; earlier refs are gone.
    snapshot = run.exchange.calls[1]["agent_context"].snapshot
    assert set(re.findall(r"^(\d+):", snapshot, re.M)) == {"2"}
    assert all(c["prompt_version"] == "agent-loop-v2" for c in run.exchange.calls)
    assert len(run.exchange.calls) == 3 and run.worker.closed
    # Every acted control carries its DOM binding; nothing restores or replays.
    assert {op.purpose for op in run.operations} <= {"setup", "explore"}
    for request in run.worker.prepares:
        if request.action.kind in {"click", "type"}:
            assert request.purpose == "explore" and request.dom_snapshot_id
            assert request.dom_element_id and request.expected_locator
        assert request.restore_checkpoint_id is None and request.replay_operation_id is None


def test_open_request_carries_agent_mode_terms_and_a_budget_for_twenty_calls(
    disposable_database, monkeypatch,
):
    run = run_agent(disposable_database, monkeypatch, [CodexStop(reason="no_safe_action")])
    opened = run.worker.open_request
    assert opened.agent_mode is True and opened.blocked_action_terms == BLOCKED_ACTION_TERMS
    assert worker_operation_budget(opened.max_states, opened.max_hops) >= 401
    assert opened.interaction_scope == "all" and opened.allowed_origins == ("https://app.test",)
    assert run.record.safe_failure_reason == "agent_stopped"
    assert [s.stop_reason for s in run.steps] == ["agent_stopped"]
    assert len(run.exchange.calls) == 1


def test_invalid_and_stale_refs_never_reach_the_worker(disposable_database, monkeypatch):
    outputs = [
        step(click("abc"), click("1:99"), click("2:1"), click("0:1"), typed("1:", "x")),
        step(click("1:1")),  # last step's version is gone
        DONE,
    ]
    run = run_agent(disposable_database, monkeypatch, outputs)
    assert [a["skipped_reason"] for a in run.steps[0].actions] == [
        "invalid_ref", "stale_ref", "stale_ref", "stale_ref", "invalid_ref"]
    assert run.steps[1].actions[0]["skipped_reason"] == "stale_ref"
    assert run.worker.explore_kinds() == []
    assert run.worker.calls.count("prepare") == 1 and run.worker.calls.count("execute") == 1


def test_a_page_outside_the_allowlist_is_observe_only(disposable_database, monkeypatch):
    outputs = [
        step(click("1:1"), typed("1:2"), AgentAction(kind="scroll", delta_y=300),
             AgentAction(kind="navigate"), AgentAction(kind="back")),
        step(AgentAction(kind="close_popup"), click("2:1")),
        DONE,
    ]
    worker = FakeWorker(None, None, page_url="https://other.test/landing")
    run = run_agent(disposable_database, monkeypatch, outputs, worker=worker)
    first, second = run.steps[0].actions, run.steps[1].actions
    assert [a.get("skipped_reason") for a in first] == ["origin_blocked"] * 4 + [None]
    assert [a.get("skipped_reason") for a in second] == [None, "origin_blocked"]
    assert run.worker.explore_kinds() == ["back", "close_popup"]


def test_the_origin_comes_from_the_page_after_a_redirect_not_from_the_target_url(
    disposable_database, monkeypatch,
):
    worker = FakeWorker(None, None, page_url=APP)
    outputs = [step(click("1:1"), click("1:1")), step(click("2:1")), DONE]

    def plan(request, n):
        # The first click lands on another origin without a popup (a redirect).
        moved = Outcome(url_change="changed", page_url="https://other.test/x")
        return moved if n == 1 else Outcome()

    worker.plan = plan
    run = run_agent(disposable_database, monkeypatch, outputs, worker=worker)
    assert run.worker.explore_kinds() == ["click"]
    assert run.steps[0].actions[1]["skipped_reason"] == "batch_stopped"
    assert run.steps[1].actions[0]["skipped_reason"] == "origin_blocked"


@pytest.mark.parametrize("variant", [
    "url_change", "fingerprint", "popup", "download", "status", "rejected",
])
def test_batch_stops_on_page_change_and_the_next_step_observes_exactly_once(
    disposable_database, monkeypatch, variant,
):
    outcome = {
        "url_change": Outcome(url_change="changed", page_url="https://app.test/next"),
        "fingerprint": Outcome(fingerprint=sha("f1")),
        "popup": Outcome(popup=True, page_url="https://app.test/popup"),
        "download": Outcome(code="download_started"),
        "status": Outcome(status="failed", code="settle_timeout"),
        "rejected": Outcome(status="rejected", code="sensitive_action_blocked"),
    }[variant]
    worker = FakeWorker(None, None)
    worker.plan = lambda request, n: outcome if n == 1 else Outcome()
    run = run_agent(disposable_database, monkeypatch,
                    [step(click("1:1"), click("1:1"), AgentAction(kind="scroll", delta_y=100)),
                     DONE], worker=worker)
    assert run.error is None
    assert run.worker.calls.count("prepare") == 2  # setup + the first click only
    first = run.steps[0]
    assert [a.get("skipped_reason") for a in first.actions] == [None, "batch_stopped",
                                                                "batch_stopped"]
    assert len(first.operation_ids) == 1 and first.stop_reason
    assert run.worker.calls.count("observe_dom") == 2  # one per step, no extra refresh
    assert len(run.exchange.calls) == 2


def test_two_typed_values_on_the_same_form_both_run(disposable_database, monkeypatch):
    run = run_agent(disposable_database, monkeypatch,
                    [step(typed("1:2", "alpha"), typed("1:3", "beta")), DONE])
    assert run.worker.explore_kinds() == ["type", "type"]
    assert run.steps[0].stop_reason is None and len(run.steps[0].operation_ids) == 2
    texts = [p.action.text for p in run.worker.prepares if p.action.kind == "type"]
    assert texts == ["alpha", "beta"] and not any("\n" in t for t in texts)
    assert all("text" not in a for a in run.steps[0].actions)  # typed values stay out of the log


def test_text_with_a_line_break_is_never_sent_to_the_worker(disposable_database, monkeypatch):
    run = run_agent(disposable_database, monkeypatch, [step(typed("1:2", "a\nb")), DONE])
    assert run.steps[0].actions[0]["skipped_reason"] == "sensitive_action_blocked"
    assert run.worker.explore_kinds() == []


def test_a_stale_observation_is_refreshed_with_a_read_only_wait(disposable_database, monkeypatch):
    worker = FakeWorker(None, None)
    worker.observe_errors = ["state_mismatch"]
    run = run_agent(disposable_database, monkeypatch, [DONE], worker=worker)
    refresh = [p for p in run.worker.prepares if p.refresh_observation]
    assert len(refresh) == 1 and refresh[0].purpose == "setup" and refresh[0].action.kind == "wait"
    assert run.record.safe_failure_reason == "agent_done"


def _redirect_worker(url, errors):
    worker = FakeWorker(None, None)
    worker.errors_after_click = list(errors)
    worker.plan = lambda request, n: (
        Outcome(url_change="changed", page_url=url, fingerprint=sha("f1"))
        if request.action.kind == "click" else Outcome())
    return worker


def _refreshes(run):
    return [p for p in run.worker.prepares if p.refresh_observation]


def test_a_stale_read_off_origin_is_refreshed_with_the_read_only_wait(
    disposable_database, monkeypatch,
):
    # r5: the click left the allowlist and observe_dom hit state_mismatch. The worker now lets
    # the read-only refresh through off-origin, so the session goes on instead of origin_blocked.
    worker = _redirect_worker("https://other.test/support", ["state_mismatch"])
    run = run_agent(disposable_database, monkeypatch, [step(click("1:1")), DONE], worker=worker)
    assert run.error is None and run.record.safe_failure_reason == "agent_done"
    assert len(_refreshes(run)) == 1 and run.worker.explore_kinds() == ["click"]
    assert not any(op.outcome_code == "origin_blocked" for op in run.operations)


def test_an_off_origin_read_that_never_settles_ends_with_its_own_reason(
    disposable_database, monkeypatch,
):
    worker = _redirect_worker("https://other.test/support", ["state_mismatch"] * 3)
    run = run_agent(disposable_database, monkeypatch, [step(click("1:1")), DONE], worker=worker)
    assert run.record.safe_failure_reason == "state_mismatch"
    assert run.worker.calls.count("observe_dom") == 1 + REFRESH_ATTEMPTS
    assert len(_refreshes(run)) == REFRESH_ATTEMPTS - 1 and run.worker.explore_kinds() == ["click"]


def test_only_the_refresh_wait_is_sent_while_the_page_is_off_origin(
    disposable_database, monkeypatch,
):
    worker = _redirect_worker("https://other.test/support", ["state_mismatch"])
    outputs = [step(click("1:1")), step(click("2:1"), typed("2:2"), wait()), DONE]
    run = run_agent(disposable_database, monkeypatch, outputs, worker=worker)
    after = [p for p in run.worker.prepares][2:]
    assert run.steps[1].actions[0]["skipped_reason"] == "origin_blocked"
    assert [(p.action.kind, p.refresh_observation) for p in after] == [("wait", True)]


def test_a_stale_read_inside_the_allowlist_still_refreshes_with_a_wait(
    disposable_database, monkeypatch,
):
    worker = _redirect_worker("https://app.test/next", ["state_mismatch"])
    run = run_agent(disposable_database, monkeypatch, [step(click("1:1")), DONE], worker=worker)
    assert len(_refreshes(run)) == 1 and run.record.safe_failure_reason == "agent_done"


# --------------------------------------------------------------------------- budget and time

def test_twenty_calls_of_ten_actions_run_inside_the_worker_budget_then_stop(
    disposable_database, monkeypatch,
):
    run = run_agent(disposable_database, monkeypatch, [step(*[wait() for _ in range(10)])])
    assert run.error is None and run.record.safe_failure_reason == "agent_step_limit"
    assert len(run.exchange.calls) == 20 and len(run.steps) == 20
    assert len(run.worker.prepares) == 201 <= worker_operation_budget(
        run.worker.open_request.max_states, run.worker.open_request.max_hops)
    assert not any(op.outcome_code == "operation_budget_exhausted" for op in run.operations)
    assert all(len(s.operation_ids) == 10 for s in run.steps)
    assert not any(p.purpose in {"restore", "replay"} for p in run.worker.prepares)


def test_history_and_memory_stay_bounded_however_many_steps_ran(disposable_database, monkeypatch):
    big = "m" * AGENT_MEMORY_MAX_CHARS
    run = run_agent(disposable_database, monkeypatch,
                    [step(wait(), memory=big, goal="g" * 500)] * 15 + [DONE],
                    policy=codex_policy(max_steps=20, max_requests_per_minute=10_000))
    bound = AGENT_MEMORY_MAX_CHARS + AGENT_HISTORY_MAX_ITEMS * AGENT_HISTORY_ITEM_MAX_CHARS
    sizes = [len(c["agent_context"].memory) + sum(len(h) for h in c["agent_context"].history)
             for c in run.exchange.calls]
    assert len(sizes) == 16 and max(sizes) <= bound
    assert all(len(c["agent_context"].history) <= 5 for c in run.exchange.calls)
    assert sizes[3] <= bound and sizes[15] <= bound
    assert len(run.exchange.calls[15]["agent_context"].history) == 5


def test_every_bridge_call_counts_including_schema_retries(disposable_database, monkeypatch):
    outputs = ["bridge_malformed_output", step(wait()), step(wait()), step(wait())]
    run = run_agent(disposable_database, monkeypatch, outputs,
                    policy=codex_policy(max_steps=3, max_requests_per_minute=10_000))
    assert len(run.exchange.calls) == 3 and len(run.steps) == 2
    assert run.record.safe_failure_reason == "agent_step_limit"
    assert [c["sequence"] for c in run.exchange.calls] == [1, 2, 3]


def test_two_schema_failures_in_a_row_end_the_session_with_the_bridge_reason(
    disposable_database, monkeypatch,
):
    run = run_agent(disposable_database, monkeypatch, ["bridge_malformed_output"])
    assert run.record.safe_failure_reason == "bridge_malformed_output"
    assert len(run.exchange.calls) == 2 and run.steps == []


def test_need_screenshot_with_consent_takes_one_more_call_with_the_image(
    disposable_database, monkeypatch,
):
    policy = codex_policy(max_steps=20, max_requests_per_minute=10_000,
                          raw_screenshot_transfer_accepted=True,
                          raw_screenshot_transfer_provider="codex_cli")
    outputs = [CodexNeedScreenshot(reason="visual_target"), DONE]
    run = run_agent(disposable_database, monkeypatch, outputs, policy=policy)
    assert [c["image"] is not None for c in run.exchange.calls] == [False, True]
    assert [c["sequence"] for c in run.exchange.calls] == [1, 2]
    assert run.record.safe_failure_reason == "agent_done"


def test_need_screenshot_without_consent_skips_the_image_stage_and_tells_the_model(
    disposable_database, monkeypatch,
):
    outputs = [CodexNeedScreenshot(reason="visual_target"), DONE]
    run = run_agent(disposable_database, monkeypatch, outputs)
    assert all(c["image"] is None for c in run.exchange.calls)
    assert len(run.exchange.calls) == 2
    assert "screenshot unavailable" in run.exchange.calls[1]["agent_context"].snapshot
    assert run.steps[0].stop_reason == "screenshot_unavailable"
    assert run.record.safe_failure_reason == "agent_done"


def test_a_model_that_only_proposes_blocked_actions_ends_at_the_limit_without_hanging(
    disposable_database, monkeypatch,
):
    run = run_agent(disposable_database, monkeypatch, [step(click("1:4"), click("1:5"))],
                    policy=codex_policy(max_steps=5, max_requests_per_minute=10_000))
    assert run.record.safe_failure_reason == "agent_step_limit"
    assert len(run.exchange.calls) == 5 and run.worker.explore_kinds() == []
    assert all(s.operation_ids == [] for s in run.steps)


def test_request_rate_per_minute_is_respected_with_a_fake_clock(disposable_database, monkeypatch):
    ticks, sleeps = [0.0], []

    async def sleep(seconds):
        sleeps.append(seconds)
        ticks[0] += seconds

    policy = codex_policy(max_steps=3, max_requests_per_minute=2)
    run = run_agent(disposable_database, monkeypatch, [step(wait()), step(wait()), step(wait())],
                    policy=policy, clock=(lambda: ticks[0], sleep), step_timeout_seconds=600)
    assert run.record.safe_failure_reason == "agent_step_limit"
    assert sleeps == [30.0, 30.0]


def test_the_worker_is_opened_within_its_max_session_seconds_in_step_mode(
    disposable_database, monkeypatch,
):
    """Regression: opening with the whole-session deadline (2400 s) gave `invalid_deadline`."""
    run = run_agent(disposable_database, monkeypatch, [step(wait()), DONE],
                    policy=codex_policy(max_steps=20), step_timeout_seconds=120)
    opened = run.worker.open_request
    assert run.record.safe_failure_reason != "visual_exploration_unavailable"
    assert opened is not None and opened.max_session_seconds == 120
    assert opened.deadline <= datetime.now(UTC) + timedelta(seconds=120)
    assert run.worker.prepares and all(p.step_deadline is not None for p in run.worker.prepares)


def test_the_worker_is_opened_within_its_max_session_seconds_without_step_mode(
    disposable_database, monkeypatch,
):
    run = run_agent(disposable_database, monkeypatch, [DONE])
    assert run.worker.open_request is not None
    assert run.record.safe_failure_reason != "visual_exploration_unavailable"


def test_every_explore_operation_reports_the_worker_parent_not_the_previous_operation(
    disposable_database, monkeypatch,
):
    """Regression (live r3): `worker_result_mismatch` on the second explore click."""
    run = run_agent(disposable_database, monkeypatch,
                    [step(click("1:1")), step(wait()), step(wait()), DONE])
    assert run.record.safe_failure_reason == "agent_done"
    root = run.worker.prepares[0].operation_id
    explore = [p for p in run.worker.prepares if p.purpose == "explore"]
    assert len(explore) >= 3
    ops = {o.id: o for o in run.uow.read_snapshot(run.scope)["operations"]}
    assert all(ops[p.operation_id].parent_operation_id == root for p in explore)


def test_the_lease_is_renewed_every_step_even_when_no_action_reaches_the_worker(
    disposable_database, monkeypatch,
):
    """Regression (live r4): steps whose actions were all blocked let the 30 s lease lapse."""
    renewals, mark = [], []

    def spy(seeded):
        real = seeded.uow.renew
        seeded.uow.renew = lambda lease, **kw: (renewals.append(1), real(lease, **kw))[1]

    blocked = step(click("1:4"), click("1:5"))
    exchange = FakeExchange([blocked, blocked, blocked, DONE],
                            on_call=lambda n: mark.append(len(renewals)) if n == 1 else None)
    run = run_agent(disposable_database, monkeypatch, [], exchange=exchange, on_seed=spy,
                    policy=codex_policy(max_steps=20, max_requests_per_minute=10_000))
    assert run.record.safe_failure_reason == "agent_done" and run.worker.explore_kinds() == []
    assert len(run.exchange.calls) == 4 and len(renewals) - mark[0] >= 3


def test_session_deadline_ends_with_session_timeout(disposable_database, monkeypatch):
    base = datetime.now(UTC)
    shift = [timedelta(0)]
    exchange = FakeExchange([step(wait(), wait()), DONE],
                            on_call=lambda n: shift.__setitem__(0, timedelta(hours=2)))
    run = run_agent(disposable_database, monkeypatch, [], exchange=exchange,
                    now=lambda: base + shift[0])
    assert run.record.safe_failure_reason == "session_timeout"
    assert len(run.exchange.calls) == 1 and run.worker.explore_kinds() == []


def test_lease_lost_mid_loop_stops_without_writing_another_step(disposable_database, monkeypatch):
    holder = {}

    def steal(count):
        if count == 2:
            with holder["seeded"].factory.begin() as db:
                db.execute(update(VisualExplorationSessionModel).where(
                    VisualExplorationSessionModel.id == holder["seeded"].scope.session_id,
                ).values(lease_owner=uuid4()))

    exchange = FakeExchange([step(wait()), step(wait()), DONE], on_call=steal)
    run = run_agent(disposable_database, monkeypatch, [], exchange=exchange,
                    on_seed=lambda seeded: holder.update(seeded=seeded))
    assert isinstance(run.error, ValueError) and "lease" in str(run.error)
    assert [s.step_index for s in run.steps] == [1]
    assert len(run.exchange.calls) == 2


def test_redelivery_after_a_crash_only_reconciles_and_never_duplicates_a_step(
    disposable_database, monkeypatch,
):
    monkeypatch.setattr("application.vision_agent_loop.decrypt_visual_intent", lambda *_: "x")
    seeded = seed(disposable_database, state="running")
    with seeded.factory.begin() as db:
        db.add(VisualAgentStepModel(
            id=uuid4(), tenant_id=seeded.scope.tenant_id, project_id=seeded.scope.project_id,
            session_id=seeded.scope.session_id, step_index=1, snapshot_version=1,
            evaluation_previous_goal="e", memory="m", next_goal="n", actions=[], operation_ids=[]))
    worker = FakeWorker(seeded.uow, seeded.scope)
    exchange = FakeExchange([DONE])
    processor = VisionAgentLoopProcessor(
        seeded.uow, worker, Settings(_env_file=None, vision_worker_secret="x"),
        lambda lease: exchange)
    event = OutboxEvent(
        id=uuid4(), tenant_id=seeded.scope.tenant_id,
        event_type="agent.visual_exploration.requested.v1", schema_version="v1",
        correlation_id=uuid4(), causation_id=None, idempotency_key="again",
        payload={"session_id": str(seeded.scope.session_id)})
    assert asyncio.run(processor.execute(event)) == "unavailable"
    record = seeded.uow.get_session(seeded.scope.tenant_id, seeded.scope.session_id)
    assert record.safe_failure_reason == "worker_state_unavailable"
    assert worker.calls == [] and exchange.calls == []
    assert [s.step_index for s in seeded.uow.agent_steps(seeded.scope)] == [1]
    assert asyncio.run(processor.execute(event)) == "already_processed"


def test_secrets_in_model_text_are_redacted_in_the_step_log(disposable_database, monkeypatch):
    secret = "password=hunter2 token=abc123"
    run = run_agent(disposable_database, monkeypatch,
                    [AgentStep(evaluation_previous_goal=secret, memory=secret, next_goal=secret,
                               actions=(wait(),)), DONE])
    saved = run.steps[0]
    for text in (saved.evaluation_previous_goal, saved.memory, saved.next_goal):
        assert "hunter2" not in text and "abc123" not in text and "[REDACTED]" in text


def test_a_lost_action_outcome_ends_the_session_but_keeps_what_ran_in_the_log(
    disposable_database, monkeypatch,
):
    worker = FakeWorker(None, None)
    worker.plan = lambda request, n: (
        Outcome("unknown", "action_outcome_unknown") if n == 2 else Outcome())
    run = run_agent(disposable_database, monkeypatch,
                    [step(click("1:1"), click("1:1"), click("1:1")), DONE], worker=worker)
    assert run.record.safe_failure_reason == "action_outcome_unknown"
    entries = run.steps[0].actions
    assert [("result" in a, "skipped_reason" in a) for a in entries[:2]] == [(True, False)] * 2
    assert len(run.steps[0].operation_ids) == 2 and len(run.steps) == 1


# --------------------------------------------------------------------------- planner untouched

def test_trace_adds_agent_step_for_agent_sessions_only(disposable_database, monkeypatch):
    run = run_agent(disposable_database, monkeypatch,
                    [step(click("1:1"), click("1:4")), DONE])
    principal = Principal("reader", {run.scope.tenant_id: frozenset({Role.TENANT_ADMIN})}, {})

    def read(engine):
        with run.factory() as db:
            if engine == "planner":
                db.execute(update(VisualExplorationSessionModel)
                           .where(VisualExplorationSessionModel.id == run.scope.session_id)
                           .values(exploration_engine="planner"))
                db.commit()
            # Production wiring (routes/vision.py::_results): the real SQL trace repository.
            return VisionResults(
                SqlAlchemyVisionRepository(db), SqlAlchemyVisualTraceRepository(db),
                run.store, SqlAlchemyAuditEventRepository(db),
            ).read_trace(
                tenant_id=run.scope.tenant_id, principal=principal,
                session_id=run.scope.session_id)

    items = read("agent_loop")["items"]
    with_step = [item for item in items if "agent_step" in item]
    assert len(with_step) == 1 and with_step[0]["purpose"] == "explore"
    summary = with_step[0]["agent_step"]
    assert summary["step_index"] == 1 and summary["next_goal"] == "goal"
    assert summary["skipped_actions"][0]["skipped_reason"] == "sensitive_action_blocked"
    assert "agent_step" not in next(item for item in items if item["purpose"] == "setup")
    assert not any("agent_step" in item for item in read("planner")["items"])


def test_trace_repository_reads_agent_steps_in_order_and_only_for_its_scope(
    disposable_database, monkeypatch,
):
    run = run_agent(disposable_database, monkeypatch, [step(wait())] * 3 + [DONE],
                    policy=codex_policy(max_steps=20, max_requests_per_minute=10_000))
    scope = run.scope
    other_project = VisualSessionScope(scope.tenant_id, uuid4(), scope.session_id)
    other_tenant = VisualSessionScope("tenant-b", scope.project_id, scope.session_id)
    with run.factory() as db:
        repo = SqlAlchemyVisualTraceRepository(db)
        # The DONE reply is recorded as the last step too (see the three-step test above).
        assert [s.step_index for s in repo.agent_steps(scope)] == [1, 2, 3, 4]
        assert repo.agent_steps(other_project) == [] and repo.agent_steps(other_tenant) == []
    assert [s.step_index for s in run.uow.agent_steps(scope)] == [1, 2, 3, 4]


def test_every_agent_operation_is_accepted_by_the_benchmark_evidence_exporter(
    disposable_database, monkeypatch,
):
    directory = Path(__file__).parents[1] / "benchmark/vision/accuracy"
    sys.path.insert(0, str(directory))
    try:
        spec = importlib.util.spec_from_file_location("agent_evidence", directory / "evidence.py")
        evidence = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(evidence)
    finally:
        sys.path.remove(str(directory))
    run = run_agent(disposable_database, monkeypatch,
                    [step(click("1:1"), typed("1:2"), wait()), DONE])
    assert len(run.operations) == 4
    for operation in run.operations:
        row = operation.model_dump(mode="json") | {"before": None, "after": None}
        exported = evidence.export_operation(row)
        assert exported["purpose"] in {"setup", "explore"} and exported["status"] == "completed"


def test_dispatch_picks_the_processor_by_engine_and_keeps_planner_default(monkeypatch):
    from infrastructure.workflows import vision_publisher

    chosen = []

    class Planner:
        def __init__(self, *_args, **_kwargs):
            pass

        async def execute(self, event):
            chosen.append("planner")
            return "done"

    class Agent(Planner):
        async def execute(self, event):
            chosen.append("agent")
            return "done"

    events = [SimpleNamespace(event_type="agent.visual_exploration.requested.v1", id=uuid4(),
                              tenant_id="t", payload={"session_id": str(uuid4())})
              for _ in range(3)]
    engines = iter(["planner", "agent_loop", None])

    class FakeUow:
        def __init__(self, *_):
            pass

        def get_session(self, tenant, session_id):
            engine = next(engines)
            record = SimpleNamespace(trace_version="v4")
            if engine:
                record.exploration_engine = engine
            return record

    class Outbox:
        def __init__(self, session):
            pass

        def list_unpublished(self, limit):
            return events

        def mark_published(self, event_id, when):
            pass

    from contextlib import contextmanager

    @contextmanager
    def transaction(factory):
        yield None

    monkeypatch.setattr(vision_publisher, "VisionTraceEventProcessor", Planner)
    monkeypatch.setattr(vision_publisher, "VisionAgentLoopProcessor", Agent)
    monkeypatch.setattr(vision_publisher, "SqlAlchemyVisualTraceUnitOfWork", FakeUow)
    monkeypatch.setattr(vision_publisher, "SqlAlchemyOutboxEventRepository", Outbox)
    monkeypatch.setattr(vision_publisher, "transactional_session", transaction)
    monkeypatch.setattr(vision_publisher, "RustFSArtifactStore", lambda *_: None)
    monkeypatch.setattr(vision_publisher, "codex_candidate_factory", lambda *_: None)
    settings = Settings(_env_file=None, vision_worker_secret="x")
    assert asyncio.run(vision_publisher.publish_vision_once(None, settings)) == 3
    assert chosen == ["planner", "agent", "planner"]
    chosen.clear()
    handler = Agent()
    engines = iter(["planner", "agent_loop"])
    events[:] = events[:2]
    asyncio.run(vision_publisher.publish_vision_once(None, settings, handler=handler))
    assert chosen == ["agent", "agent"]
