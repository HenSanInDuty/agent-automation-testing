"""Consumes durable triage requests without granting agent execution authority."""

from uuid import UUID

from agents.shared.openrouter import create_language_model
from agents.shared.runtime import AGENT_RUNTIME_CONFIG_KEY, resolve_agent_runtime
from agents.triage.executor import TriageExecutionOutcome, execute_triage
from config import Settings
from domain.ports import ConfigurationRepository, ProposalRepository, RunRepository
from domain.runs import OutboxEvent

from application.runs import GetRun
from application.triage import PersistTriageProposal


class TriageEventProcessor:
    def __init__(
        self,
        runs: RunRepository,
        configurations: ConfigurationRepository,
        proposals: ProposalRepository,
        settings: Settings,
    ) -> None:
        self._runs = runs
        self._configurations = configurations
        self._proposals = proposals
        self._settings = settings

    async def execute(self, event: OutboxEvent) -> TriageExecutionOutcome:
        if event.event_type != "agent.triage.requested.v1":
            raise ValueError("unexpected event type for triage processor")
        run_id = event.payload.get("run_id")
        if not isinstance(run_id, str):
            raise ValueError("triage event is missing run_id")
        run = GetRun(self._runs).execute(event.tenant_id, UUID(run_id))
        if run.result is None:
            return TriageExecutionOutcome(
                status="unavailable", detail="run has no deterministic result"
            )
        runtime = resolve_agent_runtime(
            self._settings,
            self._configurations.get(event.tenant_id, AGENT_RUNTIME_CONFIG_KEY),
        )
        try:
            primary = create_language_model(self._settings, runtime)
            fallback = None
            if runtime.fallback is not None:
                fallback_runtime = runtime.model_copy(
                    update={
                        "provider": runtime.fallback.provider,
                        "model": runtime.fallback.model,
                        "fallback": None,
                    }
                )
                fallback = create_language_model(self._settings, fallback_runtime)
            outcome = await execute_triage(run.result, runtime, primary, fallback)
        except ValueError:
            return TriageExecutionOutcome(
                status="unavailable", detail="triage provider is not configured"
            )
        if outcome.proposal is not None:
            PersistTriageProposal(self._proposals).execute(
                tenant_id=event.tenant_id,
                run_id=run.id,
                proposal=outcome.proposal,
                runtime=runtime,
            )
        return outcome
