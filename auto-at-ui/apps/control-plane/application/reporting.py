"""Persistence use case for immutable informational run reports."""

from uuid import UUID

from agents.shared.runtime import AgentRuntimeConfig
from auto_at.contracts.agent import RunReport, RunReportStatus
from auto_at.contracts.execution import TestExecutionResult
from domain.entities import RunReportRecord
from domain.ports import RunReportRepository


class PersistRunReport:
    def __init__(self, reports: RunReportRepository) -> None:
        self._reports = reports

    def completed(
        self,
        *,
        tenant_id: str,
        result: TestExecutionResult,
        report: RunReport,
        runtime: AgentRuntimeConfig,
        prompt_version: str,
        input_hash: str,
    ) -> RunReportRecord:
        return self._reports.add(
            RunReportRecord.create(
                tenant_id=tenant_id,
                run_id=result.run_id,
                correlation_id=result.correlation_id,
                deterministic_status=result.status,
                status=RunReportStatus.COMPLETED,
                payload=report,
                prompt_version=prompt_version,
                input_hash=input_hash,
                provenance={
                    "provider": runtime.provider,
                    "model": runtime.model,
                    "redaction_policy_version": "v1",
                },
            )
        )

    def unavailable(
        self,
        *,
        tenant_id: str,
        result: TestExecutionResult,
        prompt_version: str,
        input_hash: str,
        reason: str,
        runtime: AgentRuntimeConfig | None = None,
    ) -> RunReportRecord:
        provenance: dict[str, object] = {"safe_reason": reason, "redaction_policy_version": "v1"}
        if runtime is not None:
            provenance.update({"provider": runtime.provider, "model": runtime.model})
        return self._reports.add(
            RunReportRecord.create(
                tenant_id=tenant_id,
                run_id=result.run_id,
                correlation_id=result.correlation_id,
                deterministic_status=result.status,
                status=RunReportStatus.UNAVAILABLE,
                prompt_version=prompt_version,
                input_hash=input_hash,
                provenance=provenance,
            )
        )


class GetRunReport:
    """Read one tenant-scoped immutable advisory report."""

    def __init__(self, reports: RunReportRepository) -> None:
        self._reports = reports

    def execute(self, tenant_id: str, run_id: UUID) -> RunReportRecord | None:
        return self._reports.get_for_run(tenant_id, run_id)
