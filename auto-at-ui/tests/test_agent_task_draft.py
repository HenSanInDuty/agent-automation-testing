"""ADR-047 phase B7: the use case behind `POST /vision/explorations/{id}/test-draft`.

No database: the rows of a real-shaped agent-loop session come from the phase 08 test helper and
tiny in-memory repositories stand in for the SQL ones. The HTTP, transaction and "value only where
allowed" scans over a real database live in `test_agent_task_draft_routes.py`.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from application.agent_task_draft import (
    NEUTRAL_REQUEST,
    AgentTaskDraftNotFound,
    AgentTaskDraftRefused,
    CreateAgentTaskDraft,
    agent_task_draft_key,
)
from application.generation import GenerationStateError
from auto_at.contracts.execution import sha256_text, validate_playwright_test_source
from auto_at.contracts.generation import PlanningProvenance, request_hash
from domain.authorization import Principal, Role
from test_agent_task_trace import Rows, login_rows, stored_assessment

TENANT = "tenant-a"
NAME = "ZQ7731-name-value".ljust(24, "n")  # 24 chars: the length `login_rows` recorded
PASSWORD = "ZQ9042-word-value".ljust(24, "w")
VALUES = [NAME, PASSWORD]
ORIGIN = "https://app.test"


class Sessions:
    """`SqlAlchemyVisionRepository` over a list of session-like rows."""

    def __init__(self, *rows):
        self.rows = list(rows)

    def get(self, tenant_id, session_id):
        return next(
            (r for r in self.rows if r.id == session_id and r.tenant_id == tenant_id), None
        )

    def list_same_task(self, tenant_id, project_id, target_url, intent_hash):
        return [
            r for r in self.rows
            if (r.tenant_id, r.project_id, r.target_url, r.intent_hash)
            == (tenant_id, project_id, target_url, intent_hash)
        ]


class Trace:
    def __init__(self, rows):
        self.rows = rows

    def snapshot(self, _scope):
        return {"operations": self.rows.operations, "locators": self.rows.locators,
                "frames": self.rows.frames}

    def agent_steps(self, _scope):
        return self.rows.steps


class Generations:
    def __init__(self, *, owned=True, origins=(ORIGIN,)):
        self.policy = SimpleNamespace(allowed_origins=list(origins), vision_owned_test_target=owned)
        self.requests, self.drafts = [], []

    def get_policy(self, _tenant, _project):
        return self.policy

    def get_request_by_key(self, tenant_id, key):
        return next((r for r in self.requests
                     if r.tenant_id == tenant_id and r.idempotency_key == key), None)

    def get_draft_for_request(self, _tenant, request_id):
        return next((d for d in self.drafts if d.planning_request_id == request_id), None)

    def add_request(self, model):
        self.requests.append(model)

    def add_draft(self, model):
        self.drafts.append(model)


class Audits:
    def __init__(self):
        self.events = []

    def append(self, event):
        self.events.append(event)


def contributor(subject="requester-1", tenant=TENANT):
    return Principal(subject, {tenant: frozenset({Role.CONTRIBUTOR})}, {})


class World:
    def __init__(self, rows=None, *, owned=True, peers=(), session=None, origins=(ORIGIN,)):
        self.rows = rows or login_rows()[0]
        self.session = session or self.rows.session()
        peer_rows = [
            SimpleNamespace(id=uuid4(), tenant_id=TENANT, project_id=self.session.project_id,
                            target_url=self.session.target_url,
                            intent_hash=self.session.intent_hash, state="completed",
                            task_assessment={"status": status})
            for status in peers
        ]
        self.sessions = Sessions(self.session, *peer_rows)
        self.generations, self.audits = Generations(owned=owned, origins=origins), Audits()
        self.use_case = CreateAgentTaskDraft(
            self.sessions, Trace(self.rows), self.generations, self.audits,
            consistency_threshold=0.9,
        )

    def create(self, values=VALUES, principal=None, session_id=None, **options):
        return self.use_case.execute(
            tenant_id=options.pop("tenant_id", TENANT),
            principal=principal or contributor(),
            session_id=session_id or self.session.id,
            input_values=values,
            **options,
        )

    def refusal(self, values=VALUES, **options) -> AgentTaskDraftRefused:
        with pytest.raises(AgentTaskDraftRefused) as caught:
            self.create(values, **options)
        self.assert_nothing_written()
        return caught.value

    def assert_nothing_written(self):
        assert (self.generations.requests, self.generations.drafts, self.audits.events) == (
            [], [], [])


# ----------------------------------------------------------------------- the happy path


def test_a_draft_is_made_from_the_session_with_the_values_in_step_order():
    world = World()
    result = world.create()
    draft = result.draft
    assert result.created is True and draft.state == "pending_review"
    source = draft.playwright_test_source
    validate_playwright_test_source(source)
    assert source.index(NAME) < source.index(PASSWORD)
    assert draft.source_hash == sha256_text(source)
    assert (draft.linked_test_case_id, draft.linked_run_id) == (None, None)
    assert draft.planning_request_id == result.request.id
    assert draft.correlation_id == result.request.correlation_id


def test_the_request_row_is_a_completed_fixed_neutral_sentence_without_task_or_values():
    world = World()
    request = world.create().request
    assert request.state == "completed" and request.failure_reason is None
    assert request.redacted_request == NEUTRAL_REQUEST
    assert request.request_hash == request_hash(NEUTRAL_REQUEST)
    assert request.vision_handoff_id is None
    assert request.target_url == world.session.target_url
    assert request.project_id == world.session.project_id
    assert request.idempotency_key == agent_task_draft_key(
        world.session.id, world.rows.build().trace_hash)


def test_provenance_names_the_trace_the_flags_the_requester_and_the_consistency():
    world = World(peers=["achieved", "achieved"])
    provenance = world.create().draft.provenance
    trace = world.rows.build()
    assert provenance["agent_trace_source"] == {
        "session_id": str(world.session.id), "trace_hash": trace.trace_hash}
    assert provenance["contains_test_values"] is True
    assert provenance["owned_test_target"] is True
    assert provenance["requested_by"] == "requester-1"
    assert provenance["consistency"] == {
        "schema_version": "v1", "assessed_sessions": 3, "group_sessions": 3,
        "agreement_rate": 1.0, "modal_status": "achieved", "threshold": 0.9,
        "small_sample": False}
    # Everything the contract knows still validates; `consistency` is the one stored extra.
    PlanningProvenance.model_validate(
        {k: v for k, v in provenance.items() if k != "consistency"})


def test_both_audit_events_name_the_requester_never_the_system_and_hold_only_ids():
    world = World()
    result = world.create(correlation_id=uuid4())
    events = world.audits.events
    assert [e.action for e in events] == ["generation.requested", "generation.completed"]
    for event in events:
        assert event.actor == "requester-1" and event.actor != "system"
        assert event.entity_type == "generation_request" and event.entity_id == result.request.id
        assert event.correlation_id == result.request.correlation_id
        assert event.tenant_id == TENANT
        assert NAME not in repr(event) and PASSWORD not in repr(event)


def test_a_chain_without_a_type_step_needs_no_flag_and_carries_no_values():
    rows = Rows()
    rows.op("navigate", purpose="setup")
    clicked = rows.op("click", name="Open")
    rows.step(1, clicked)
    world = World(rows, owned=False)
    result = world.create(())
    provenance = result.draft.provenance
    assert provenance["contains_test_values"] is False
    assert provenance["owned_test_target"] is False  # the flag as it was when the draft was made


def test_the_draft_exists_only_as_a_request_a_draft_and_two_audits():
    world = World()
    world.create()
    assert (len(world.generations.requests), len(world.generations.drafts),
            len(world.audits.events)) == (1, 1, 2)


# ----------------------------------------------------------------------- idempotency


def test_a_second_call_returns_the_first_draft_without_looking_at_the_values():
    world = World()
    first = world.create()
    for again in (VALUES, [], ["different"], ["x" * 24, "y" * 24]):
        second = world.create(again)
        assert second.created is False
        assert second.draft is first.draft and second.request is first.request
    assert (len(world.generations.requests), len(world.audits.events)) == (1, 2)


def test_the_key_depends_on_the_session_and_the_trace_only():
    world = World()
    trace_hash = world.rows.build().trace_hash
    assert agent_task_draft_key(world.session.id, trace_hash) == \
        agent_task_draft_key(world.session.id, trace_hash)
    assert agent_task_draft_key(world.session.id, trace_hash) != \
        agent_task_draft_key(uuid4(), trace_hash)
    assert agent_task_draft_key(world.session.id, trace_hash) != \
        agent_task_draft_key(world.session.id, "f" * 64)
    assert NAME not in world.create().request.idempotency_key


def test_a_key_that_belongs_to_another_request_is_a_conflict_not_a_replay():
    world = World()
    world.create()
    world.generations.requests[0].target_url = "https://elsewhere.test/"
    with pytest.raises(GenerationStateError):
        world.create()
    world.generations.requests[0].target_url = world.session.target_url
    world.generations.drafts.clear()  # a request that lost its draft is not a replay either
    with pytest.raises(GenerationStateError):
        world.create()


def test_a_changed_trace_is_a_new_draft():
    world = World()
    first = world.create()
    world.rows.step(9, world.rows.op("click", name="Another"))
    second = world.create()
    assert second.created is True and second.draft.id != first.draft.id
    assert len(world.generations.requests) == 2


# ----------------------------------------------------------------------- refusals write nothing


@pytest.mark.parametrize(
    ("override", "code"),
    [
        ({"state": "running"}, "session_not_completed"),
        ({"state": "unavailable"}, "session_not_completed"),
        ({"exploration_engine": "planner"}, "assessment_unavailable"),
        ({"task_assessment": None}, "assessment_unavailable"),
        ({"task_assessment": {"status": "surprise"}}, "assessment_unavailable"),
    ],
)
def test_a_session_that_cannot_back_a_draft_is_refused_with_its_code(override, code):
    rows = login_rows()[0]
    world = World(rows, session=rows.session(**override))
    assert world.refusal().code == code


@pytest.mark.parametrize("status", ["not_achieved", "blocked", "inconclusive"])
def test_only_an_achieved_assessment_may_become_a_draft(status):
    rows = login_rows()[0]
    assessment = stored_assessment("blocked") | {"status": status}
    world = World(rows, session=rows.session(task_assessment=assessment))
    assert world.refusal().code == "assessment_not_achieved"


def test_an_inconsistent_group_is_refused_and_the_report_explains_it():
    world = World(peers=["achieved", "achieved", "achieved", "not_achieved"])
    error = world.refusal()
    assert error.code == "assessment_inconsistent"
    assert error.report["agreement_rate"] == 0.8 and error.report["threshold"] == 0.9
    assert error.report["status_counts"]["not_achieved"] == 1
    assert world.refusal(["x"]).code == "assessment_inconsistent"  # before any value is looked at


def test_a_modal_status_that_is_not_achieved_is_refused_as_inconsistent():
    world = World(peers=["not_achieved"] * 4)
    assert world.refusal().code == "assessment_inconsistent"


@pytest.mark.parametrize("origins", [("https://other.test",), ()])
def test_an_origin_outside_the_project_allowlist_is_refused(origins):
    assert World(origins=origins).refusal().code == "origin_not_allowed"


def test_a_project_without_a_policy_row_is_refused():
    world = World()
    world.generations.get_policy = lambda *_: None
    assert world.refusal().code == "origin_not_allowed"


def test_a_type_step_needs_the_owned_test_target_flag_before_any_value_is_read():
    world = World(owned=False)
    assert world.refusal().code == "input_value_not_allowed"
    assert world.refusal([]).code == "input_value_not_allowed"


def test_a_missing_value_names_the_first_step_that_has_none():
    world = World()
    error = world.refusal([NAME])
    assert error.code == "input_value_missing"
    steps = world.rows.build().steps
    assert error.step_index == steps[1].step_index and error.operation_id == steps[1].operation_id
    assert world.refusal([]).code == "input_value_missing"


@pytest.mark.parametrize("values", [[NAME[:-1], PASSWORD], [NAME, PASSWORD + "w"], [NAME, ""]])
def test_a_value_of_another_length_than_the_session_recorded_is_refused(values):
    assert World().refusal(values).code == "input_value_mismatch"


def test_a_value_no_step_asked_for_is_refused():
    assert World().refusal([*VALUES, "extra"]).code == "input_value_mismatch"


def test_a_value_that_the_source_policy_rejects_is_refused_without_echoing_it():
    bad = "process.exit(1)".ljust(24, " ")
    error = World().refusal([bad, PASSWORD])
    assert error.code in {"input_value_rejected_by_source_policy", "source_policy_rejected"}
    assert bad not in repr(error.__dict__) and bad.strip() not in str(error)


@pytest.mark.parametrize(
    ("build", "code"),
    [
        (lambda rows: rows.frames.pop(), "evidence_expired"),
        (lambda rows: rows.locators.clear(), "locator_unavailable"),
    ],
)
def test_evidence_that_is_gone_is_refused_and_a_trace_refusal_keeps_its_step(build, code):
    rows = login_rows()[0]
    build(rows)
    error = World(rows).refusal()
    assert error.code == code


def test_a_trace_refusal_names_the_step_and_operation():
    rows = Rows()
    rows.op("navigate", purpose="setup")
    broken = rows.op("click", name="Open", locator="absent")
    rows.step(1, broken)
    error = World(rows).refusal(())
    assert error.code == "locator_unavailable"
    assert (error.step_index, error.operation_id) == (1, broken.id)


# ----------------------------------------------------------------------- who may ask


@pytest.mark.parametrize(
    "principal",
    [
        Principal("viewer-1", {TENANT: frozenset({Role.VIEWER})}, {}),  # READ only
        Principal("reviewer-1", {TENANT: frozenset({Role.REVIEWER})}, {}),
        Principal("svc", {TENANT: frozenset({Role.SERVICE})}, {}, is_service=True),
        Principal("other-tenant", {"tenant-b": frozenset({Role.TENANT_ADMIN})}, {}),
        Principal("nobody", {}, {}),
    ],
)
def test_a_principal_without_submit_generation_gets_not_found_and_nothing_is_written(principal):
    world = World()
    with pytest.raises(AgentTaskDraftNotFound):
        world.create(principal=principal)
    world.assert_nothing_written()


def test_a_grant_on_another_project_does_not_reach_this_session():
    world = World()
    other_project = Principal("pm", {}, {(TENANT, uuid4()): frozenset({Role.PROJECT_ADMIN})})
    with pytest.raises(AgentTaskDraftNotFound):
        world.create(principal=other_project)
    grant = {(TENANT, world.session.project_id): frozenset({Role.PROJECT_ADMIN})}
    mine = Principal("pm", {}, grant)
    assert world.create(principal=mine).created is True


def test_a_missing_session_and_another_tenant_are_not_found():
    world = World()
    with pytest.raises(AgentTaskDraftNotFound):
        world.create(session_id=uuid4())
    with pytest.raises(AgentTaskDraftNotFound):
        world.create(tenant_id="tenant-b", principal=contributor(tenant="tenant-b"))
    world.assert_nothing_written()


# ------------------------------------------------------------ the value stays in the source


def everything_but_the_source(world, result) -> str:
    draft = result.draft
    parts = [repr(result.request.__dict__), repr(world.audits.events), repr(draft.title),
             repr(draft.assumptions), repr(draft.stop_conditions), repr(draft.provenance),
             repr(draft.source_hash), repr(draft.correlation_id)]
    return "\n".join(parts)


def test_the_value_is_in_the_draft_source_and_in_nothing_else_the_use_case_writes():
    world = World()
    result = world.create()
    assert NAME in result.draft.playwright_test_source
    assert PASSWORD in result.draft.playwright_test_source
    rest = everything_but_the_source(world, result)
    assert NAME not in rest and PASSWORD not in rest
    assert "ZQ7731" not in rest and "ZQ9042" not in rest


@pytest.mark.parametrize(
    "values",
    [
        [NAME[:-1], PASSWORD],
        [NAME],
        [],
        [*VALUES, "extra-zq"],
        ["process.exit(1)".ljust(24), PASSWORD],
    ],
)
def test_no_refusal_carries_a_value(values):
    world = World()
    error = world.refusal(values)
    text = " ".join([str(error), repr(error), repr(error.__dict__), repr(error.args)])
    for secret in (*values, NAME, PASSWORD, "ZQ7731", "ZQ9042"):
        if secret.strip():
            assert secret not in text


def test_a_replay_with_the_same_values_does_not_change_what_is_stored():
    world = World()
    first = world.create()
    before = repr(first.draft.__dict__)
    world.create(VALUES)
    assert repr(first.draft.__dict__) == before
