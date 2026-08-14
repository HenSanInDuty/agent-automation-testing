"""Consumes durable run-report events without granting agents execution authority."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID

from agents.reporting.executor import ReportingExecutionOutcome, execute_run_reporting
from agents.shared.evidence import VerifiedArtifactTextReader, build_run_report_evidence_bundle
from agents.shared.models import LanguageModel
from agents.shared.openrouter import create_language_model
from agents.shared.runtime import (
    AGENT_RUNTIME_CONFIG_KEY,
    AgentRuntimeConfig,
    resolve_agent_runtime,
)
from auto_at.contracts.events import EventType
from auto_at.contracts.execution import validate_playwright_test_source
from config import Settings
from domain.activity import ActivityEvent
from domain.ports import (
    ActivityEventRepository,
    ArtifactRepository,
    ConfigurationRepository,
    RunReportRepository,
    RunRepository,
)
from domain.runs import OutboxEvent

from application.reporting import PersistRunReport
from application.runs import GetRun

logger = logging.getLogger(__name__)


class ReportingEventProcessor:
    """At-least-once-safe terminal reporting over bounded verified evidence."""

    def __init__(
        self,
        runs: RunRepository,
        configurations: ConfigurationRepository,
        artifacts: ArtifactRepository,
        reports: RunReportRepository,
        reader: VerifiedArtifactTextReader,
        settings: Settings,
        activities: ActivityEventRepository | None = None,
        model_factory: Callable[[Settings, AgentRuntimeConfig], LanguageModel] = (
            create_language_model
        ),
    ) -> None:
        self._runs = runs
        self._configurations = configurations
        self._artifacts = artifacts
        self._reports = reports
        self._reader = reader
        self._settings = settings
        self._activities = activities
        self._model_factory = model_factory

    async def execute(self, event: OutboxEvent) -> ReportingExecutionOutcome:
        if event.event_type != EventType.AGENT_RUN_REPORT_REQUESTED.value:
            raise ValueError("unexpected event type for reporting processor")
        run_id = event.payload.get("run_id")
        if not isinstance(run_id, str):
            raise ValueError("run-report event is missing run_id")
        run = GetRun(self._runs).execute(event.tenant_id, UUID(run_id))
        existing = self._reports.get_for_run(event.tenant_id, run.id)
        if existing is not None:
            return ReportingExecutionOutcome(
                status=existing.status.value,
                report=existing.payload,
                detail="existing report reused",
            )
        if run.result is None:
            return ReportingExecutionOutcome(
                status="unavailable", detail="run has no deterministic result"
            )

        started = perf_counter()
        self._record(run, "requested", "running", "AI post-run review started.")
        runtime = self._runtime(event.tenant_id)
        evidence = build_run_report_evidence_bundle(
            self._review_result(run),
            runtime.evidence,
            self._artifacts.list_for_run(event.tenant_id, run.id),
            self._reader,
        )
        try:
            primary = self._model_factory(self._settings, runtime)
            fallback = self._fallback(runtime)
            outcome = await execute_run_reporting(run.result, evidence, runtime, primary, fallback)
        except ValueError:
            outcome = ReportingExecutionOutcome(
                status="unavailable", detail="reporting provider is not configured"
            )

        persistence = PersistRunReport(self._reports)
        if outcome.report is not None:
            persistence.completed(
                tenant_id=event.tenant_id,
                result=run.result,
                report=outcome.report,
                runtime=runtime,
                prompt_version=self._settings.agent_reporting_prompt_version,
                input_hash=evidence.input_hash,
            )
            self._record(run, "completed", "passed", "AI post-run review was recorded.")
            final = outcome
        else:
            persistence.unavailable(
                tenant_id=event.tenant_id,
                result=run.result,
                prompt_version=self._settings.agent_reporting_prompt_version,
                input_hash=evidence.input_hash,
                reason=outcome.detail or "reporting unavailable",
                runtime=runtime,
            )
            self._record(run, "unavailable", "unavailable", "AI post-run review is unavailable.")
            final = ReportingExecutionOutcome(status="unavailable", detail=outcome.detail)
        logger.info(
            "run_report.completed run_id=%s correlation_id=%s status=%s latency_seconds=%.3f",
            run.id,
            run.correlation_id,
            final.status,
            perf_counter() - started,
        )
        return final

    @staticmethod
    def _review_result(run):
        """Expose only approved, policy-valid source to the read-only review agent."""
        assert run.result is not None
        source = None if run.request is None else run.request.runner_config.get(
            "playwright_test_source"
        )
        if not isinstance(source, str):
            return run.result
        try:
            validate_playwright_test_source(source)
        except ValueError:
            return run.result
        metadata = {
            **run.result.runner_metadata,
            "review_context": {
                "approved_playwright_test_source": source,
                "source_hash": run.request.runner_config.get("source_hash"),
                "review_scope": (
                    "Compare approved source with deterministic result; do not change verdict."
                ),
            },
        }
        return run.result.model_copy(update={"runner_metadata": metadata})

    def _runtime(self, tenant_id: str) -> AgentRuntimeConfig:
        return resolve_agent_runtime(
            self._settings,
            self._configurations.get(tenant_id, AGENT_RUNTIME_CONFIG_KEY),
        )

    def _fallback(self, runtime: AgentRuntimeConfig) -> LanguageModel | None:
        if runtime.fallback is None:
            return None
        fallback_runtime = runtime.model_copy(
            update={
                "provider": runtime.fallback.provider,
                "model": runtime.fallback.model,
                "fallback": None,
            }
        )
        return self._model_factory(self._settings, fallback_runtime)

    def _record(self, run, stage: str, status: str, summary: str) -> None:
        if self._activities is not None:
            self._activities.append(
                ActivityEvent.create(
                    tenant_id=run.tenant_id,
                    run_id=run.id,
                    correlation_id=run.correlation_id,
                    source="reporting",
                    stage=stage,
                    status=status,
                    safe_summary=summary,
                    occurred_at=datetime.now(UTC),
                )
            )
