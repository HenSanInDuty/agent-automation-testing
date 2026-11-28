"""ADR-047 phase 13: review boundary and guards for drafts that carry typed test values.

Route tests run on a disposable PostgreSQL database (fixture on 127.0.0.1:55437, skipped when it
is absent) so "nothing changed after a refusal" is a row count, not a mock assertion.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from agents.shared.evidence import build_run_report_evidence_bundle
from agents.shared.runtime import EvidencePolicy
from api.v1.routes import generation, runs
from application.generation import DecideGeneratedDraft, GenerationStateError
from auto_at.contracts.execution import (
    Artifact,
    RunStatus,
    TargetType,
    TestExecutionRequest,
    TestExecutionResult,
    sha256_text,
)
from config import Settings, get_settings
from domain.entities import ArtifactRecord
from fastapi import FastAPI
from fastapi.testclient import TestClient
from infrastructure.persistence.models import (
    AuditEventModel,
    Base,
    GeneratedTestDecisionModel,
    GeneratedTestDraftModel,
    GenerationRequestModel,
    OutboxEventModel,
    ProjectExecutionPolicyModel,
    ProjectModel,
    TestCaseModel,
    TestRunModel,
)
from infrastructure.runners import RunnerUnavailableError
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from vision_trace_fixtures import disposable_database  # noqa: F401  (pytest fixture)

TENANT = "tenant-a"
ORIGIN = "https://fixture.test"
VALUE = "zk-7731-sample"  # the "typed value": must never reach generation_requests or a model
SOURCE = (
    "import { test, expect } from '@playwright/test';\n"
    "test('login', async ({ page }) => {\n"
    f"  await page.goto('{ORIGIN}/');\n"
    f"  await page.getByLabel('Ten dang nhap').fill('{VALUE}');\n"
    "});\n"
)
PLAIN_SOURCE = (
    "import { test } from '@playwright/test';\n"
    f"test('home', async ({{ page }}) => {{ await page.goto('{ORIGIN}/'); }});\n"
)
REQUESTER = "requester-1"


def headers(actor: str, roles: str) -> dict[str, str]:
    return {"X-Tenant-Id": TENANT, "X-Actor-Id": actor, "X-Actor-Roles": roles}


def provenance(*, agent=True, values=True, requester=REQUESTER) -> dict:
    data = {
        "provider": "deterministic", "model": "renderer", "prompt_version": "none",
        "redaction_policy_version": "v1",
    }
    if agent:
        data |= {
            "agent_trace_source": {"session_id": str(uuid4()), "trace_hash": "a" * 64},
            "contains_test_values": values, "owned_test_target": True,
            "requested_by": requester,
        }
    return data


class Preflight:
    """Stands in for the pinned worker; `fail` makes the source fail to load."""

    fail = False

    def __init__(self, *_):
        pass

    def preflight(self, _request):
        if Preflight.fail:
            raise RunnerUnavailableError("generated source failed Playwright preflight")


@pytest.fixture
def world(disposable_database, monkeypatch):  # noqa: F811
    Base.metadata.create_all(disposable_database)
    factory = sessionmaker(disposable_database, expire_on_commit=False)
    Preflight.fail = False
    for module in (generation, runs):
        monkeypatch.setattr(module, "create_session_factory", lambda _settings: factory)
    monkeypatch.setattr(generation, "HttpPlaywrightTransport", Preflight)
    app = FastAPI()
    app.include_router(generation.router, prefix="/api/v1")
    app.include_router(runs.router, prefix="/api/v1")
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, codex_bridge_enabled=False,
    )
    project = uuid4()
    with factory.begin() as db:
        db.add(ProjectModel(id=project, tenant_id=TENANT, name="P", default_target="web_ui"))
        db.flush()
    with TestClient(app, raise_server_exceptions=False) as client:
        yield SimpleNamespace(client=client, factory=factory, project=project)


def set_flag(world, owned: bool) -> None:
    with world.factory.begin() as db:
        db.merge(ProjectExecutionPolicyModel(
            tenant_id=TENANT, project_id=world.project, allowed_origins=[ORIGIN],
            vision_max_hops=5, vision_max_states=50, vision_owned_test_target=owned,
        ))


def add_draft(world, *, source=SOURCE, prov=None) -> UUID:
    request_id, draft_id = uuid4(), uuid4()
    with world.factory.begin() as db:
        db.add(GenerationRequestModel(
            id=request_id, tenant_id=TENANT, project_id=world.project, correlation_id=uuid4(),
            target_url=f"{ORIGIN}/", redacted_request="seed", request_hash="b" * 64,
            state="completed", idempotency_key=f"seed-{request_id}",
        ))
        db.flush()
        db.add(GeneratedTestDraftModel(
            id=draft_id, tenant_id=TENANT, planning_request_id=request_id,
            correlation_id=uuid4(), state="pending_review", title="t",
            playwright_test_source=source, source_hash=sha256_text(source), assumptions=[],
            stop_conditions=[], provenance=prov if prov is not None else provenance(),
        ))
    return draft_id


def count(world, model) -> int:
    with world.factory() as db:
        return db.scalar(select(func.count()).select_from(model))


def snapshot(world) -> dict[str, int]:
    return {
        m.__tablename__: count(world, m)
        for m in (TestCaseModel, TestRunModel, GeneratedTestDecisionModel,
                  GenerationRequestModel, OutboxEventModel, AuditEventModel)
    }


def decide(world, draft_id, actor="reviewer-1", roles="reviewer", **body):
    return world.client.post(
        f"/api/v1/test-generations/drafts/{draft_id}/decision",
        json={"approved": True, **body}, headers=headers(actor, roles),
    )


def draft_state(world, draft_id) -> str:
    with world.factory() as db:
        return db.get(GeneratedTestDraftModel, draft_id).state


# ----------------------------------------------------- criterion 1: reviewer boundary


def test_reviewer_other_than_requester_approves_and_creates_case_and_run(world):
    set_flag(world, True)
    draft_id = add_draft(world)
    before = snapshot(world)
    response = decide(world, draft_id, acknowledge_disposable_credentials=True)
    assert response.status_code == 200, response.text
    after = snapshot(world)
    assert after["test_cases"] == before["test_cases"] + 1
    assert after["test_runs"] == before["test_runs"] + 1
    assert after["generated_test_decisions"] == 1
    with world.factory() as db:
        case = db.scalars(select(TestCaseModel)).one()
        assert case.specification["contains_test_values"] is True
    assert draft_state(world, draft_id) == "approved"


@pytest.mark.parametrize("roles", ["project_admin", "tenant_admin"])
def test_admin_roles_with_proposal_permission_can_approve(world, roles):
    set_flag(world, True)
    draft_id = add_draft(world)
    assert decide(world, draft_id, "admin-1", roles,
                  acknowledge_disposable_credentials=True).status_code == 200


def test_requester_cannot_approve_own_draft_and_nothing_changes(world):
    set_flag(world, True)
    draft_id = add_draft(world)
    before = snapshot(world)
    response = decide(world, draft_id, REQUESTER, "project_admin",
                      acknowledge_disposable_credentials=True)
    assert response.status_code == 409
    assert response.json()["detail"] == "reviewer_must_differ_from_requester"
    assert snapshot(world) == before
    assert draft_state(world, draft_id) == "pending_review"


def test_agent_draft_without_requester_fails_closed(world):
    set_flag(world, True)
    prov = provenance()
    del prov["requested_by"]
    draft_id = add_draft(world, prov=prov)
    before = snapshot(world)
    response = decide(world, draft_id, acknowledge_disposable_credentials=True)
    assert response.status_code == 409 and snapshot(world) == before


def test_contributor_lacks_proposal_permission_and_nothing_changes(world):
    set_flag(world, True)
    draft_id = add_draft(world)
    before = snapshot(world)
    response = decide(world, draft_id, "someone-else", "contributor",
                      acknowledge_disposable_credentials=True)
    assert response.status_code == 404
    assert snapshot(world) == before and draft_state(world, draft_id) == "pending_review"


@pytest.mark.parametrize("roles", ["service", "reviewer,service", "tenant_admin,service"])
def test_service_principal_cannot_decide_an_agent_draft(world, roles):
    set_flag(world, True)
    draft_id = add_draft(world)
    before = snapshot(world)
    response = decide(world, draft_id, "svc", roles, acknowledge_disposable_credentials=True)
    assert response.status_code == 404
    assert snapshot(world) == before


def test_rejection_by_reviewer_creates_no_case_or_run(world):
    set_flag(world, True)
    draft_id = add_draft(world)
    response = decide(world, draft_id, approved=False, reason="no")
    assert response.status_code == 200 and draft_state(world, draft_id) == "rejected"
    snap = snapshot(world)
    assert snap["test_cases"] == 0 and snap["test_runs"] == 0


def test_the_use_case_is_the_only_path_to_a_case_and_run(world):
    """Every refusal above leaves both tables empty; only an approved decision fills them."""
    set_flag(world, True)
    draft_id = add_draft(world)
    for roles, actor in (("contributor", "x"), ("service", "y"), ("viewer", "z")):
        assert decide(world, draft_id, actor, roles,
                      acknowledge_disposable_credentials=True).status_code == 404
    snap = snapshot(world)
    assert snap["test_cases"] == 0 and snap["test_runs"] == 0


# ----------------------------------------------------- criterion 2: acknowledgement and flag


def test_missing_acknowledgement_is_refused_and_nothing_changes(world):
    set_flag(world, True)
    draft_id = add_draft(world)
    before = snapshot(world)
    response = decide(world, draft_id)
    assert response.status_code == 409
    assert response.json()["detail"] == "disposable_credentials_ack_required"
    assert snapshot(world) == before and draft_state(world, draft_id) == "pending_review"


def test_acknowledgement_false_is_refused(world):
    set_flag(world, True)
    draft_id = add_draft(world)
    assert decide(world, draft_id, acknowledge_disposable_credentials=False).status_code == 409


def test_acknowledged_but_flag_switched_off_is_refused(world):
    set_flag(world, False)
    draft_id = add_draft(world)
    before = snapshot(world)
    response = decide(world, draft_id, acknowledge_disposable_credentials=True)
    assert response.status_code == 409
    assert response.json()["detail"] == "owned_test_target_disabled"
    assert snapshot(world) == before


def test_agent_draft_without_values_needs_reviewer_but_no_acknowledgement(world):
    set_flag(world, False)
    draft_id = add_draft(world, source=PLAIN_SOURCE, prov=provenance(values=False))
    assert decide(world, draft_id, "someone", "contributor").status_code == 404
    assert decide(world, draft_id, REQUESTER, "tenant_admin").status_code == 409
    assert decide(world, draft_id).status_code == 200
    with world.factory() as db:
        assert "contains_test_values" not in db.scalars(select(TestCaseModel)).one().specification


def test_legacy_draft_is_decided_as_before_by_a_contributor(world):
    set_flag(world, False)
    draft_id = add_draft(world, source=PLAIN_SOURCE, prov=provenance(agent=False))
    assert decide(world, draft_id, REQUESTER, "contributor").status_code == 200
    with world.factory() as db:
        assert db.scalars(select(TestCaseModel)).one().specification.keys() == {
            "playwright_test_source", "source_hash", "generated_draft_id"}


# ----------------------------------------------------- criterion 3 and 4: model-path guards


def test_failed_preflight_of_a_values_draft_is_refused_without_a_repair_request(world):
    set_flag(world, True)
    draft_id = add_draft(world)
    Preflight.fail = True
    before = snapshot(world)
    response = decide(world, draft_id, acknowledge_disposable_credentials=True)
    assert response.status_code == 409
    assert response.json()["detail"] == "credentials_in_source"
    assert snapshot(world) == before  # no generation_requests row, no outbox event
    assert draft_state(world, draft_id) == "pending_review"
    with world.factory() as db:
        assert not db.scalars(
            select(GenerationRequestModel).where(
                GenerationRequestModel.redacted_request.contains(VALUE))
        ).all()


def test_failed_preflight_of_a_legacy_draft_still_queues_a_repair_request(world):
    set_flag(world, False)
    draft_id = add_draft(world, source=PLAIN_SOURCE, prov=provenance(agent=False))
    Preflight.fail = True
    before = snapshot(world)
    response = decide(world, draft_id, "x", "contributor")
    assert response.status_code == 200 and response.json()["preflight_repair_request_id"]
    after = snapshot(world)
    assert after["generation_requests"] == before["generation_requests"] + 1
    assert after["test_cases"] == 0 and after["test_runs"] == 0


def failed_run(world, *, values: bool) -> UUID:
    """A failed run of an approved generated case, inserted as the approval would leave it."""
    source = SOURCE if values else PLAIN_SOURCE
    case_id, run_id = f"generated-{uuid4()}", uuid4()
    request = TestExecutionRequest(
        run_id=run_id, project_id=world.project, test_case_id=case_id,
        target_type=TargetType.WEB_UI, target_url=f"{ORIGIN}/", revision=sha256_text(source),
    )
    result = TestExecutionResult(
        run_id=run_id, correlation_id=request.correlation_id, status=RunStatus.FAILED,
        started_at="2026-11-27T00:00:00Z", completed_at="2026-11-27T00:00:01Z",
        summary="Assertion failed.",
    )
    spec = {"playwright_test_source": source, "source_hash": sha256_text(source)}
    if values:
        spec["contains_test_values"] = True
    with world.factory.begin() as db:
        db.add(TestCaseModel(
            id=case_id, tenant_id=TENANT, project_id=world.project, target_type="web_ui",
            revision=sha256_text(source), specification=spec, name="case",
        ))
        db.flush()
        db.add(TestRunModel(
            id=run_id, tenant_id=TENANT, project_id=world.project, test_case_id=case_id,
            revision=sha256_text(source), status="failed",
            correlation_id=request.correlation_id, request=request.model_dump(mode="json"),
            result=result.model_dump(mode="json"), created_at=datetime.now(UTC),
        ))
    return run_id


def revise(world, run_id):
    return world.client.post(
        f"/api/v1/runs/{run_id}/revised-draft",
        headers={**headers("someone", "contributor"), "Idempotency-Key": uuid4().hex},
    )


def test_revised_draft_of_a_values_case_is_refused_with_409(world):
    set_flag(world, True)
    run_id = failed_run(world, values=True)
    before = snapshot(world)
    response = revise(world, run_id)
    assert response.status_code == 409 and response.json()["detail"] == "credentials_in_source"
    assert snapshot(world) == before
    assert count(world, GenerationRequestModel) == 0


def test_revised_draft_of_another_case_keeps_the_old_behaviour(world):
    set_flag(world, False)
    run_id = failed_run(world, values=False)
    response = revise(world, run_id)
    assert response.status_code == 202, response.text
    assert count(world, GenerationRequestModel) == 1


def test_no_path_of_this_phase_stores_the_value_in_generation_requests(world):
    set_flag(world, True)
    draft_id = add_draft(world)
    Preflight.fail = True
    decide(world, draft_id, acknowledge_disposable_credentials=True)       # preflight guard
    revise(world, failed_run(world, values=True))                           # revised-draft guard
    Preflight.fail = False
    assert decide(world, draft_id, acknowledge_disposable_credentials=True).status_code == 200
    with world.factory() as db:
        stored = db.scalars(select(GenerationRequestModel.redacted_request)).all()
        outbox = db.scalars(select(OutboxEventModel.payload)).all()
    assert all(VALUE not in text and "Approved source" not in text for text in stored)
    # The value is accepted at the dispatch places (ADR-047 Q10) but not in generation_requests.
    assert any(VALUE in str(payload) for payload in outbox)


# ----------------------------------------------------- use case without HTTP


class MemoryRepository:
    def __init__(self, draft, request, owned=True):
        self.draft, self.request, self.owned = draft, request, owned
        self.cases, self.decisions, self.requests = [], [], []

    def get_draft(self, *_):
        return self.draft

    def get_decision(self, *_):
        return None

    def get_request(self, *_):
        return self.request

    def get_policy(self, *_):
        return SimpleNamespace(allowed_origins=[ORIGIN], vision_owned_test_target=self.owned)

    def add_test_case(self, case):
        self.cases.append(case)

    def add_decision(self, decision):
        self.decisions.append(decision)

    def add_request(self, request):
        self.requests.append(request)

    def get_request_by_key(self, *_):
        return None


def memory_draft(prov):
    return SimpleNamespace(
        id=uuid4(), planning_request_id=uuid4(), playwright_test_source=SOURCE,
        source_hash=sha256_text(SOURCE), state="pending_review", provenance=prov,
        linked_test_case_id=None, linked_run_id=None, correlation_id=uuid4(), title="t",
    )


def run_use_case(repository, **overrides):
    values = dict(tenant_id=TENANT, draft_id=repository.draft.id, approved=True,
                  decided_by="reviewer-1", reason=None,
                  acknowledge_disposable_credentials=True) | overrides
    return DecideGeneratedDraft(repository, [], [], object()).execute(**values)


@pytest.mark.parametrize(("overrides", "owned", "code"), [
    ({"decided_by": REQUESTER}, True, "reviewer_must_differ_from_requester"),
    ({"acknowledge_disposable_credentials": False}, True, "disposable_credentials_ack_required"),
    ({}, False, "owned_test_target_disabled"),
])
def test_use_case_refuses_before_any_write(overrides, owned, code):
    request = SimpleNamespace(project_id=uuid4(), correlation_id=uuid4(), target_url=f"{ORIGIN}/")
    repository = MemoryRepository(memory_draft(provenance()), request, owned)
    with pytest.raises(GenerationStateError, match=code):
        run_use_case(repository, **overrides)
    assert not repository.cases and not repository.decisions and not repository.requests
    assert repository.draft.state == "pending_review"


# ----------------------------------------------------- criterion 5: evidence excerpts

FAIL_OUTPUT = (
    "  1) login.spec.ts:3:1 > login\n\n    Error: expect(locator).toBeVisible()\n\n"
    "       at login.spec.ts:5\n\n"
    "      3 | test('login', async ({ page }) => {\n"
    f"      4 |   await page.getByLabel('Ten dang nhap').fill('{VALUE}');\n"
    "    > 5 |   await expect(page.getByText('Welcome')).toBeVisible();\n"
    "        |                                           ^\n"
    "      6 | });\n"
)
WORKER_RESULT = f'{{"status": "failed", "error": "step fill({VALUE}) failed"}}'


class Reader:
    def __init__(self, files):
        self.files = files

    def read_verified_bytes(self, artifact, max_bytes):
        return self.files[artifact.kind].encode()[:max_bytes]


def evidence(*, contains_test_values=None):
    run_id = uuid4()
    artifacts = [
        Artifact(kind="playwright-output", uri="s3://b/out.txt", content_type="text/plain"),
        Artifact(kind="worker-result", uri="s3://b/res.json", content_type="application/json"),
    ]
    result = TestExecutionResult(
        run_id=run_id, correlation_id=uuid4(), status=RunStatus.FAILED,
        started_at="2026-11-27T00:00:00Z", completed_at="2026-11-27T00:00:01Z",
        summary="Assertion failed.", artifacts=artifacts,
        runner_metadata={"review_context": {"approved_playwright_test_source": SOURCE},
                         "workflow": "w"},
    )
    records = [
        ArtifactRecord(id=uuid4(), tenant_id=TENANT, run_id=run_id, kind=a.kind, uri=a.uri,
                       checksum="c" * 64, size=10, content_type=a.content_type)
        for a in artifacts
    ]
    reader = Reader({"playwright-output": FAIL_OUTPUT, "worker-result": WORKER_RESULT})
    kwargs = {} if contains_test_values is None else {"contains_test_values": contains_test_values}
    return build_run_report_evidence_bundle(result, EvidencePolicy(), records, reader, **kwargs)


def test_values_run_sends_no_artifact_excerpt_and_no_source_to_the_model():
    bundle = evidence(contains_test_values=True)
    assert bundle.excerpts == []
    dumped = bundle.model_dump_json()
    assert VALUE not in dumped and "approved_playwright_test_source" not in dumped
    assert bundle.runner_metadata == {"workflow": "w"}  # the rest of the metadata is unchanged


@pytest.mark.parametrize("flag", [None, False])
def test_run_without_values_keeps_the_old_evidence(flag):
    bundle = evidence(contains_test_values=flag)
    assert {e.kind for e in bundle.excerpts} == {"playwright-output", "worker-result"}
    # The premise of the guard: pattern redaction does not catch a literal value.
    assert any(VALUE in e.text for e in bundle.excerpts)
    assert "review_context" in bundle.runner_metadata


def test_input_hash_differs_so_a_stored_report_is_not_confused_across_the_modes():
    assert evidence(contains_test_values=True).input_hash != evidence().input_hash
