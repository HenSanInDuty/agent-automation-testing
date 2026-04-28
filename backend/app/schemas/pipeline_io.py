"""
schemas/pipeline_io.py
──────────────────────
Pydantic models representing the structured data flowing between pipeline stages.

Flow:
    Document file
        → [Ingestion]  → IngestionOutput  (list of RequirementItem)
        → [Test Case]  → TestCaseOutput   (list of TestCase + coverage)
        → [Execution]  → ExecutionOutput  (list of TestExecutionResult + summary)
        → [Reporting]  → PipelineReport   (coverage + root cause + executive summary)
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# Shared enums
# ─────────────────────────────────────────────────────────────────────────────


class RequirementType(str, Enum):
    FUNCTIONAL = "functional"
    NON_FUNCTIONAL = "non_functional"
    CONSTRAINT = "constraint"
    ASSUMPTION = "assumption"


class TestType(str, Enum):
    API = "api"
    UI = "ui"
    INTEGRATION = "integration"
    UNIT = "unit"


class TestCategory(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    EDGE_CASE = "edge_case"
    BOUNDARY = "boundary"


class ExecutionStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class RootCauseCategory(str, Enum):
    AUTHENTICATION = "authentication"
    DATA = "data"
    LOGIC = "logic"
    ENVIRONMENT = "environment"
    NETWORK = "network"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 – Ingestion output
# ─────────────────────────────────────────────────────────────────────────────


class RequirementItem(BaseModel):
    """A single software requirement extracted from the source document."""

    id: str = Field(default="TBD", description="Auto-assigned: REQ-001, REQ-002, …")
    title: str = Field(description="Short descriptive title")
    description: str = Field(description="Full requirement description")
    type: RequirementType = RequirementType.FUNCTIONAL
    priority: str = Field(default="medium", description="high | medium | low")
    tags: list[str] = Field(default_factory=list)
    notes: str = Field(default="", description="Ambiguities or missing information")
    raw_text: str = Field(default="", description="Original text from document")
    source_chunk: Optional[str] = Field(
        default=None, description="Chunk index where the requirement was found"
    )


class IngestionOutput(BaseModel):
    """Output of the Ingestion pipeline stage."""

    requirements: list[RequirementItem] = Field(default_factory=list)
    document_name: str
    total_requirements: int = 0
    chunks_processed: int = 0
    processing_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def sync_total(self) -> "IngestionOutput":
        if self.total_requirements == 0 and self.requirements:
            self.total_requirements = len(self.requirements)
        return self


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 – Test Case Generation output
# ─────────────────────────────────────────────────────────────────────────────


class TestStep(BaseModel):
    """A single action step within a test case."""

    step_number: int
    action: str = Field(description="What to do in this step")
    expected_result: str = Field(description="What should happen after this step")


class TestCase(BaseModel):
    """A single test case generated from a requirement."""

    id: str = Field(description="TC-001, TC-002, …")
    requirement_id: str = Field(
        description="Traceability: maps back to RequirementItem.id"
    )
    title: str
    description: str = ""
    preconditions: str = ""
    steps: list[TestStep] = Field(default_factory=list)
    expected_result: str = ""

    test_type: TestType = TestType.API
    category: TestCategory = TestCategory.POSITIVE
    priority: str = "medium"
    tags: list[str] = Field(default_factory=list)

    # Automation metadata
    automation_script: Optional[str] = None

    # API-specific fields
    api_endpoint: Optional[str] = None
    http_method: Optional[str] = None
    request_headers: Optional[dict[str, str]] = None
    request_body: Optional[dict[str, Any]] = None
    expected_status_code: Optional[int] = None

    # UI-specific fields
    ui_page: Optional[str] = None
    ui_selector: Optional[str] = None


class CoverageSummary(BaseModel):
    """Coverage metrics for the generated test suite."""

    total_requirements: int = 0
    covered_requirements: int = 0
    coverage_percentage: float = 0.0
    uncovered_requirements: list[str] = Field(default_factory=list)
    by_type: dict[str, int] = Field(default_factory=dict)
    by_priority: dict[str, int] = Field(default_factory=dict)
    by_category: dict[str, int] = Field(default_factory=dict)
    coverage_gaps: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def compute_percentage(self) -> "CoverageSummary":
        if self.coverage_percentage == 0.0 and self.total_requirements > 0:
            self.coverage_percentage = round(
                self.covered_requirements / self.total_requirements * 100, 1
            )
        return self


class AutomationReadiness(BaseModel):
    total_automated: int = 0
    automation_percentage: float = 0.0
    frameworks_used: list[str] = Field(default_factory=list)


class TestCaseOutput(BaseModel):
    """Output of the Test Case Generation crew."""

    test_cases: list[TestCase] = Field(default_factory=list)
    total_test_cases: int = 0
    coverage_summary: CoverageSummary = Field(default_factory=CoverageSummary)
    automation_readiness: AutomationReadiness = Field(
        default_factory=AutomationReadiness
    )
    design_notes: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def sync_total(self) -> "TestCaseOutput":
        if self.total_test_cases == 0 and self.test_cases:
            self.total_test_cases = len(self.test_cases)
        return self


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3 – Execution output
# ─────────────────────────────────────────────────────────────────────────────


class TestExecutionResult(BaseModel):
    """Execution result for a single test case."""

    test_case_id: str
    status: ExecutionStatus
    duration_ms: float = 0.0
    actual_result: str = ""
    actual_status_code: Optional[int] = None
    actual_response: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    timestamp: datetime = Field(default_factory=_utcnow)
    logs: list[str] = Field(default_factory=list)


class ExecutionSummary(BaseModel):
    """Aggregate statistics for the execution run."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    pass_rate: float = 0.0
    duration_seconds: float = 0.0

    @model_validator(mode="after")
    def compute_pass_rate(self) -> "ExecutionSummary":
        if self.pass_rate == 0.0 and self.total > 0:
            self.pass_rate = round(self.passed / self.total * 100, 1)
        return self


class TimingStats(BaseModel):
    """Timing statistics across all test executions."""

    min_ms: float = 0.0
    max_ms: float = 0.0
    avg_ms: float = 0.0
    p95_ms: float = 0.0


class FailurePattern(BaseModel):
    """A recurring failure pattern identified by the execution logger."""

    pattern: str
    affected_tests: list[str] = Field(default_factory=list)
    occurrence_count: int = 0


class ExecutionOutput(BaseModel):
    """Output of the Execution crew."""

    results: list[TestExecutionResult] = Field(default_factory=list)
    summary: ExecutionSummary = Field(default_factory=ExecutionSummary)
    environment: str = "default"
    timing_stats: TimingStats = Field(default_factory=TimingStats)
    failure_patterns: list[FailurePattern] = Field(default_factory=list)
    execution_notes: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Stage 4 – Reporting output
# ─────────────────────────────────────────────────────────────────────────────


class RequirementCoverageDetail(BaseModel):
    """Per-requirement post-execution coverage detail."""

    requirement_id: str
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    coverage_status: str = "uncovered"  # covered | partial | uncovered


class PostExecutionCoverage(BaseModel):
    """Post-execution coverage analysis (richer than pre-execution CoverageSummary)."""

    total_requirements: int = 0
    covered_requirements: int = 0
    validated_requirements: int = 0
    coverage_percentage: float = 0.0
    validation_percentage: float = 0.0
    uncovered_requirements: list[str] = Field(default_factory=list)
    failed_requirements: list[str] = Field(default_factory=list)
    by_type: dict[str, int] = Field(default_factory=dict)
    by_priority: dict[str, int] = Field(default_factory=dict)
    requirement_details: list[RequirementCoverageDetail] = Field(default_factory=list)


class RootCause(BaseModel):
    """A root cause analysis entry for one or more failed test cases."""

    test_case_id: str
    failure_pattern: str
    probable_cause: str
    root_cause_category: RootCauseCategory = RootCauseCategory.UNKNOWN
    recommendation: str
    affected_tests: list[str] = Field(default_factory=list)
    severity: Severity = Severity.MEDIUM
    suggested_fix: str = ""


class PipelineReport(BaseModel):
    """Final output of the Reporting crew — the end-to-end pipeline result."""

    # Coverage
    coverage_percentage: float = 0.0
    coverage_analysis: PostExecutionCoverage = Field(
        default_factory=PostExecutionCoverage
    )

    # Failures
    root_cause_analysis: list[RootCause] = Field(default_factory=list)

    # Human-readable
    executive_summary: str = ""
    recommendations: list[str] = Field(default_factory=list)
    risk_items: list[str] = Field(default_factory=list)

    # Metrics
    total_test_cases: int = 0
    pass_rate: float = 0.0
    metrics: dict[str, Any] = Field(default_factory=dict)

    # Timestamp
    generated_at: datetime = Field(default_factory=_utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# Convenience: full pipeline result (all stages combined)
# ─────────────────────────────────────────────────────────────────────────────


class PipelineRunResult(BaseModel):
    """
    Complete result of a single pipeline run.
    Stored in the database and returned by GET /api/v1/pipeline/runs/{run_id}.
    """

    run_id: str
    document_name: str

    ingestion: Optional[IngestionOutput] = None
    testcase: Optional[TestCaseOutput] = None
    execution: Optional[ExecutionOutput] = None
    report: Optional[PipelineReport] = None

    started_at: datetime = Field(default_factory=_utcnow)
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    status: str = "pending"  # pending | running | completed | failed
    error: Optional[str] = None

    @model_validator(mode="after")
    def compute_duration(self) -> "PipelineRunResult":
        if self.finished_at and self.started_at and self.duration_seconds is None:
            delta = self.finished_at - self.started_at
            self.duration_seconds = round(delta.total_seconds(), 2)
        return self
