from types import SimpleNamespace
from uuid import uuid4

from application.generation import DecideGeneratedDraft
from auto_at.contracts.execution import sha256_text
from auto_at.contracts.generation import DraftState
from infrastructure.runners import RunnerUnavailableError


class Repository:
    def __init__(self, draft, request) -> None:
        self.draft = draft
        self.request = request
        self.decisions = []
        self.test_cases = []
        self.requests = []

    def get_draft(self, _tenant_id, _draft_id):
        return self.draft

    def get_decision(self, _tenant_id, _draft_id):
        return None

    def get_request(self, _tenant_id, _request_id):
        return self.request

    def get_policy(self, _tenant_id, _project_id):
        return SimpleNamespace(allowed_origins=["https://example.test"])

    def get_request_by_key(self, _tenant_id, idempotency_key):
        return next(
            (item for item in self.requests if item.idempotency_key == idempotency_key), None
        )

    def add_request(self, request):
        self.requests.append(request)

    def add_decision(self, decision):
        self.decisions.append(decision)

    def add_test_case(self, test_case):
        self.test_cases.append(test_case)


class Preflight:
    def __init__(self) -> None:
        self.request = None

    def preflight(self, request) -> None:
        self.request = request
        raise RunnerUnavailableError("generated source failed Playwright preflight")


def test_failed_preflight_queues_a_revised_draft_without_creating_a_run() -> None:
    source = "import { test } from '@playwright/test';\ntest('home', async () => {});"
    project_id = uuid4()
    draft = SimpleNamespace(
        id=uuid4(),
        planning_request_id=uuid4(),
        playwright_test_source=source,
        source_hash=sha256_text(source),
        state=DraftState.PENDING_REVIEW.value,
        linked_test_case_id=None,
        linked_run_id=None,
    )
    request = SimpleNamespace(
        project_id=project_id, correlation_id=uuid4(), target_url="https://example.test"
    )
    repository = Repository(draft, request)
    preflight = Preflight()

    use_case = DecideGeneratedDraft(repository, [], [], object(), preflight)
    decided, decision, repair = use_case.execute(
        tenant_id="tenant-a",
        draft_id=draft.id,
        approved=True,
        decided_by="reviewer-a",
        reason=None,
    )

    assert decided is draft
    assert decision is None
    assert repair is not None
    assert repair.request_id == repository.requests[0].id
    assert preflight.request is not None
    assert preflight.request.project_id == project_id
    assert draft.state == DraftState.PENDING_REVIEW.value
    assert repository.decisions == []
    assert repository.test_cases == []
    assert repository.requests[0].state == "queued"
    assert "failed non-browser preflight" in repository.requests[0].redacted_request
