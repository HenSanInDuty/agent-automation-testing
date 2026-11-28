"""ADR-047 phase B7: a Playwright draft from a completed agent-loop session, in one transaction.

Wires the earlier phases: the task trace (phase 08), the consistency report (09), the deterministic
renderer (11). It writes a `completed` generation request, a `pending_review` draft and two audit
events, and nothing else: no test case, no run, no outbox event, no model call. Approval, preflight
and the run stay on `DecideGeneratedDraft` (phase 13).

The caller owns the transaction. The typed values (Q1) arrive in `input_values`, go to the renderer
and end up only in the draft source. The request row holds a fixed neutral sentence, the audit
events hold ids, the provenance holds hashes, flags and counts, the idempotency key hashes only
`session_id` and `trace_hash`, and a refusal carries a code and a step place, never a value.
"""

from dataclasses import dataclass
from uuid import UUID, uuid4

from auto_at.contracts.execution import sha256_text
from auto_at.contracts.generation import (
    AgentTraceSource,
    DraftState,
    PlanningProvenance,
    ProjectExecutionPolicy,
    request_hash,
)
from domain.agent_task_trace import AgentTaskTraceRefused
from domain.authorization import (
    AuthorizationError,
    Permission,
    Principal,
    actor_for_tenant,
    require,
)
from domain.runs import AuditEvent
from domain.vision import VisualSessionScope
from infrastructure.persistence.models import (
    GeneratedTestDraftModel,
    GenerationRequestModel,
)

from application.agent_task_consistency import read_consistency
from application.agent_task_renderer import (
    AgentTaskRenderRefused,
    has_test_values,
    render_agent_task_source,
    typed_steps,
)
from application.agent_task_trace import AgentTaskTraceNotFound, read_agent_task_trace
from application.generation import GenerationStateError
from application.vision_replay import VisionReplayNotFoundError

# The one text `generation_requests.redacted_request` ever holds for this kind of draft: no task
# wording and no value, so nothing here can leak either.
NEUTRAL_REQUEST = "Deterministic draft rendered from a completed agent-loop session trace."
_PROVIDER, _MODEL, _PROMPT_VERSION, _REDACTION_VERSION = (
    "deterministic",
    "agent-task-renderer",
    "none",
    "v1",
)
_CONSISTENCY_KEYS = (
    "schema_version",
    "assessed_sessions",
    "group_sessions",
    "agreement_rate",
    "modal_status",
    "threshold",
    "small_sample",
)
_NOT_ACHIEVED = frozenset({"not_achieved", "blocked", "inconclusive"})


class AgentTaskDraftNotFound(LookupError):
    """Missing session, other tenant, or no right to ask: the three are not told apart."""


class AgentTaskDraftRefused(ValueError):
    """The draft cannot be made. `code` says why; the rest says where. Never holds a value."""

    def __init__(
        self,
        code: str,
        *,
        step_index: int | None = None,
        operation_id: UUID | None = None,
        report: dict | None = None,
    ) -> None:
        super().__init__(code)
        self.code, self.step_index, self.operation_id = code, step_index, operation_id
        self.report = report


@dataclass(frozen=True)
class AgentTaskDraftResult:
    request: GenerationRequestModel
    draft: GeneratedTestDraftModel
    created: bool  # False: an earlier call for the same session and trace already made the draft


def agent_task_draft_key(session_id: UUID, trace_hash: str) -> str:
    """Idempotency key: the session and its trace only, so a replay never hashes a value."""
    return request_hash(f"agent-task-draft-v1:{session_id}:{trace_hash}")


class _DraftSession:
    """The two checks `POST` and `GET .../test-draft/inputs` share: one copy of the rules.

    Needs `self._sessions` and `self._trace`."""

    @staticmethod
    def _check_assessment(record) -> None:
        """Only a finished agent-loop session with an `achieved` assessment may become a draft."""
        if record.state != "completed":
            raise AgentTaskDraftRefused("session_not_completed")
        stored = record.task_assessment
        if record.exploration_engine != "agent_loop" or not isinstance(stored, dict):
            raise AgentTaskDraftRefused("assessment_unavailable")
        status = stored.get("status")
        if status in _NOT_ACHIEVED:
            raise AgentTaskDraftRefused("assessment_not_achieved")  # Q9: no expected-fail draft
        if status != "achieved":
            raise AgentTaskDraftRefused("assessment_unavailable")

    def _read_trace(self, scope: VisualSessionScope):
        try:
            return read_agent_task_trace(self._sessions, self._trace, scope)
        except AgentTaskTraceNotFound:
            raise AgentTaskDraftNotFound from None
        except AgentTaskTraceRefused as error:
            # The builder cannot tell a deleted frame from a broken chain; both mean "no evidence".
            code = "evidence_expired" if error.code == "evidence_unavailable" else error.code
            raise AgentTaskDraftRefused(
                code, step_index=error.step_index, operation_id=error.operation_id
            ) from None


class CreateAgentTaskDraft(_DraftSession):
    """`sessions`: `SqlAlchemyVisionRepository`; `trace`: `SqlAlchemyVisualTraceRepository`;
    `generations`: `SqlAlchemyGenerationRepository`; `audits`: an audit repository."""

    def __init__(self, sessions, trace, generations, audits, *, consistency_threshold: float):
        self._sessions, self._trace = sessions, trace
        self._generations, self._audits = generations, audits
        self._threshold = consistency_threshold

    def execute(
        self,
        *,
        tenant_id: str,
        principal: Principal,
        session_id: UUID,
        input_values: tuple[str, ...] | list[str],
        correlation_id: UUID | None = None,
    ) -> AgentTaskDraftResult:
        record = self._sessions.get(tenant_id, session_id)
        if record is None:
            raise AgentTaskDraftNotFound
        try:
            actor = actor_for_tenant(principal, tenant_id, record.project_id)
            require(actor, Permission.SUBMIT_GENERATION)
        except AuthorizationError:
            raise AgentTaskDraftNotFound from None
        self._check_assessment(record)
        scope = VisualSessionScope(tenant_id, record.project_id, session_id)
        trace = self._read_trace(scope)
        key = agent_task_draft_key(session_id, trace.trace_hash)
        existing = self._generations.get_request_by_key(tenant_id, key)
        if existing is not None:
            return self._replay(existing, record, tenant_id)
        report = self._consistency(tenant_id, principal, session_id)
        policy = self._generations.get_policy(tenant_id, record.project_id)
        if policy is None or not self._origin_allowed(record.project_id, policy, trace.target_url):
            raise AgentTaskDraftRefused("origin_not_allowed")
        has_values = has_test_values(trace)
        owned = bool(policy.vision_owned_test_target)
        if has_values and not owned:
            raise AgentTaskDraftRefused("input_value_not_allowed")
        try:
            output = render_agent_task_source(trace, input_values)
        except AgentTaskRenderRefused as error:
            raise AgentTaskDraftRefused(
                error.code, step_index=error.step_index, operation_id=error.operation_id
            ) from None
        correlation_id = correlation_id or uuid4()
        request = GenerationRequestModel(
            id=uuid4(),
            tenant_id=tenant_id,
            project_id=record.project_id,
            correlation_id=correlation_id,
            target_url=trace.target_url,
            redacted_request=NEUTRAL_REQUEST,
            request_hash=request_hash(NEUTRAL_REQUEST),
            state="completed",
            failure_reason=None,
            idempotency_key=key,
            vision_handoff_id=None,
        )
        provenance = PlanningProvenance(
            provider=_PROVIDER,
            model=_MODEL,
            prompt_version=_PROMPT_VERSION,
            redaction_policy_version=_REDACTION_VERSION,
            agent_trace_source=AgentTraceSource(
                session_id=session_id, trace_hash=trace.trace_hash
            ),
            contains_test_values=has_values,
            owned_test_target=owned,
            requested_by=actor.subject,
        ).model_dump(mode="json")
        # ponytail: `PlanningProvenance` has no `consistency` field (the contract file is outside
        # this phase) and the column is free JSON, so the counts are merged into the stored dict.
        provenance["consistency"] = {name: report[name] for name in _CONSISTENCY_KEYS}
        draft = GeneratedTestDraftModel(
            id=uuid4(),
            tenant_id=tenant_id,
            planning_request_id=request.id,
            correlation_id=correlation_id,
            state=DraftState.PENDING_REVIEW.value,
            title=output.title,
            playwright_test_source=output.playwright_test_source,
            source_hash=sha256_text(output.playwright_test_source),
            assumptions=output.assumptions,
            stop_conditions=output.stop_conditions,
            provenance=provenance,
            linked_test_case_id=None,
            linked_run_id=None,
        )
        self._generations.add_request(request)
        self._generations.add_draft(draft)
        for action in ("generation.requested", "generation.completed"):
            self._audits.append(
                AuditEvent(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    actor=actor.subject,
                    action=action,
                    entity_type="generation_request",
                    entity_id=request.id,
                    correlation_id=correlation_id,
                )
            )
        return AgentTaskDraftResult(request, draft, True)

    def _consistency(self, tenant_id: str, principal: Principal, session_id: UUID) -> dict:
        try:
            report = read_consistency(
                self._sessions,
                tenant_id=tenant_id,
                principal=principal,
                session_id=session_id,
                threshold=self._threshold,
            )
        except VisionReplayNotFoundError:
            raise AgentTaskDraftNotFound from None
        if not report["eligible"]:
            raise AgentTaskDraftRefused("assessment_inconsistent", report=report)
        return report

    @staticmethod
    def _origin_allowed(project_id: UUID, policy, target_url: str) -> bool:
        try:
            return ProjectExecutionPolicy(
                project_id=project_id, allowed_origins=policy.allowed_origins
            ).allows(target_url)
        except ValueError:
            return False

    def _replay(self, existing, record, tenant_id: str) -> AgentTaskDraftResult:
        """The same session and trace asked again: hand back the draft, compare nothing typed."""
        draft = self._generations.get_draft_for_request(tenant_id, existing.id)
        if (
            draft is None
            or existing.project_id != record.project_id
            or existing.target_url != record.target_url
            or existing.request_hash != request_hash(NEUTRAL_REQUEST)
        ):
            raise GenerationStateError("idempotency key belongs to a different request")
        return AgentTaskDraftResult(existing, draft, False)


@dataclass(frozen=True)
class AgentTaskDraftInputs:
    owned_test_target: bool
    type_steps: tuple[tuple[int, str, int], ...]  # (step_index, locator_name, text_chars)
    has_type_steps: bool = False  # true even when the flag is off: no length, only that one exists


class ReadAgentTaskDraftInputs(_DraftSession):
    """What the requester must type: the length each `type` step expects (ADR-047 Q1).

    Same session, trace and checks as `CreateAgentTaskDraft`. Writes nothing and holds no value.

    Without the project's owned-test-target flag the list is empty, as `POST` would refuse the
    values (`input_value_not_allowed`); a length is never shown to a project that may not type.
    `has_type_steps` is still answered, so the caller can tell "nothing to type" (a draft with
    `values: []` is allowed) from "typing needed but not allowed" (`POST` refuses).
    Consistency is not asked here (that is `POST` and `/consistency`)."""

    def __init__(self, sessions, trace, generations):
        self._sessions, self._trace, self._generations = sessions, trace, generations

    def execute(
        self, *, tenant_id: str, principal: Principal, session_id: UUID
    ) -> AgentTaskDraftInputs:
        record = self._sessions.get(tenant_id, session_id)
        if record is None:
            raise AgentTaskDraftNotFound
        try:
            require(
                actor_for_tenant(principal, tenant_id, record.project_id),
                Permission.SUBMIT_GENERATION,
            )
        except AuthorizationError:
            raise AgentTaskDraftNotFound from None
        self._check_assessment(record)
        trace = self._read_trace(VisualSessionScope(tenant_id, record.project_id, session_id))
        has_type_steps = has_test_values(trace)
        policy = self._generations.get_policy(tenant_id, record.project_id)
        if policy is None or not policy.vision_owned_test_target:
            return AgentTaskDraftInputs(False, (), has_type_steps)
        return AgentTaskDraftInputs(
            True,
            tuple(
                (step.step_index, step.locator.value, step.text_chars)
                for step in typed_steps(trace)
            ),
            has_type_steps,
        )
