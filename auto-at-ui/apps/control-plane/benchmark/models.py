"""Versioned, deliberately small schemas for the offline benchmark."""

from enum import StrEnum
from typing import Literal

from auto_at.contracts.agent import TriageCategory
from pydantic import BaseModel, Field, model_validator


class ExperimentCondition(StrEnum):
    BASELINE = "baseline"
    SINGLE_AGENT_TRIAGE = "single_agent_triage"
    MULTI_AGENT_TRIAGE_HEALING = "multi_agent_triage_healing"
    SELECTED_EVIDENCE_ABLATION = "selected_evidence_ablation"


class BenchmarkPins(BaseModel):
    browser: str = Field(min_length=1)
    runner_image: str = Field(min_length=1)
    test_revision: str = Field(min_length=7)
    environment: dict[str, str] = Field(min_length=1)


class ScenarioExpectation(BaseModel):
    baseline_status: Literal["passed", "failed", "errored"]
    root_cause: TriageCategory
    healing_applicable: bool


class ConditionObservation(BaseModel):
    predicted_root_cause: TriageCategory | None = None
    healing_proposed: bool = False
    healing_validated: bool = False
    triage_ms: int = Field(default=0, ge=0)
    recovery_ms: int = Field(default=0, ge=0)
    token_cost_usd: float = Field(default=0, ge=0)
    evidence_used: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validated_healing_must_be_proposed(self) -> "ConditionObservation":
        if self.healing_validated and not self.healing_proposed:
            raise ValueError("a healing cannot be validated unless it was proposed")
        return self


class BenchmarkScenario(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    fault_type: Literal["locator", "dom", "text", "timing", "product", "environment", "flaky"]
    title: str = Field(min_length=1)
    target: str = Field(min_length=1)
    inputs: dict[str, str] = Field(min_length=1)
    seed: str = Field(min_length=1)
    expected: ScenarioExpectation
    evidence_references: list[str] = Field(min_length=1)
    observations: dict[ExperimentCondition, ConditionObservation]


class BenchmarkManifest(BaseModel):
    contract_version: Literal["v1"] = "v1"
    id: str = Field(min_length=1)
    pins: BenchmarkPins
    repetitions: int = Field(ge=2, le=100)
    reproducibility_tolerance_ms: int = Field(ge=0)
    scenarios: list[BenchmarkScenario] = Field(min_length=7)

    @model_validator(mode="after")
    def scenarios_cover_every_required_fault_and_condition(self) -> "BenchmarkManifest":
        expected_faults = {"locator", "dom", "text", "timing", "product", "environment", "flaky"}
        ids = [scenario.id for scenario in self.scenarios]
        if len(ids) != len(set(ids)):
            raise ValueError("scenario IDs must be unique")
        if {scenario.fault_type for scenario in self.scenarios} != expected_faults:
            raise ValueError(
                "manifest must cover every controlled fault type exactly at least once"
            )
        conditions = set(ExperimentCondition)
        for scenario in self.scenarios:
            if set(scenario.observations) != conditions:
                raise ValueError(f"scenario {scenario.id} must define every experiment condition")
            if scenario.observations[ExperimentCondition.BASELINE].predicted_root_cause is not None:
                raise ValueError("the deterministic baseline has no agent classification")
        return self


class BenchmarkResult(BaseModel):
    contract_version: Literal["v1"] = "v1"
    manifest_id: str
    scenario_id: str
    condition: ExperimentCondition
    repetition: int = Field(ge=1)
    deterministic_status: Literal["passed", "failed", "errored"]
    expected_root_cause: TriageCategory
    predicted_root_cause: TriageCategory | None = None
    healing_proposed: bool
    healing_validated: bool
    triage_ms: int
    recovery_ms: int
    duration_ms: int = Field(ge=0)
    token_cost_usd: float = Field(ge=0)
    evidence_references: list[str]
    reproducibility_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class MetricSummary(BaseModel):
    condition: ExperimentCondition
    classification_precision: float | None = None
    classification_recall: float | None = None
    classification_f1: float | None = None
    valid_healing_rate: float | None = None
    false_healing_rate: float | None = None
    median_triage_ms: float | None = None
    median_recovery_ms: float | None = None
    median_overhead_ms: float
    token_cost_usd: float
    repeatability: float
