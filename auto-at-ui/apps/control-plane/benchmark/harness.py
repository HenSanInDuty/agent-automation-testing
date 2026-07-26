"""Pure experiment runner; inputs and outputs are stable across fresh local runs."""

from hashlib import sha256
from statistics import median

from benchmark.models import (
    BenchmarkManifest,
    BenchmarkResult,
    ExperimentCondition,
    MetricSummary,
)


def fingerprint(
    manifest: BenchmarkManifest, scenario_id: str, condition: ExperimentCondition
) -> str:
    value = "|".join(
        [
            manifest.contract_version,
            manifest.id,
            manifest.pins.test_revision,
            scenario_id,
            condition.value,
        ]
    )
    return sha256(value.encode()).hexdigest()


def run_experiments(manifest: BenchmarkManifest) -> list[BenchmarkResult]:
    """Materialise declared controlled observations without invoking a model or changing a test."""
    results: list[BenchmarkResult] = []
    for repetition in range(1, manifest.repetitions + 1):
        for scenario in manifest.scenarios:
            for condition, observation in scenario.observations.items():
                baseline_duration = 100
                duration = baseline_duration + observation.triage_ms + observation.recovery_ms
                results.append(
                    BenchmarkResult(
                        manifest_id=manifest.id,
                        scenario_id=scenario.id,
                        condition=condition,
                        repetition=repetition,
                        deterministic_status=scenario.expected.baseline_status,
                        expected_root_cause=scenario.expected.root_cause,
                        predicted_root_cause=observation.predicted_root_cause,
                        healing_proposed=observation.healing_proposed,
                        healing_validated=observation.healing_validated,
                        triage_ms=observation.triage_ms,
                        recovery_ms=observation.recovery_ms,
                        duration_ms=duration,
                        token_cost_usd=observation.token_cost_usd,
                        evidence_references=(
                            observation.evidence_used or scenario.evidence_references
                        ),
                        reproducibility_fingerprint=fingerprint(manifest, scenario.id, condition),
                    )
                )
    return results


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def calculate_metrics(results: list[BenchmarkResult]) -> list[MetricSummary]:
    summaries: list[MetricSummary] = []
    for condition in ExperimentCondition:
        rows = [result for result in results if result.condition == condition]
        classified = [row for row in rows if row.predicted_root_cause is not None]
        correct = sum(row.predicted_root_cause == row.expected_root_cause for row in classified)
        precision = _ratio(correct, len(classified))
        recall = _ratio(correct, len(rows)) if classified else None
        f1 = None
        if precision is not None and recall is not None and precision + recall:
            f1 = round(2 * precision * recall / (precision + recall), 6)
        proposed = [row for row in rows if row.healing_proposed]
        valid = [row for row in proposed if row.healing_validated]
        fingerprints = {
            (row.scenario_id, row.condition, row.reproducibility_fingerprint) for row in rows
        }
        scenario_conditions = {(row.scenario_id, row.condition) for row in rows}
        summaries.append(
            MetricSummary(
                condition=condition,
                classification_precision=precision,
                classification_recall=recall,
                classification_f1=f1,
                valid_healing_rate=_ratio(len(valid), len(proposed)),
                false_healing_rate=_ratio(len(proposed) - len(valid), len(proposed)),
                median_triage_ms=median([row.triage_ms for row in rows]) if classified else None,
                median_recovery_ms=median([row.recovery_ms for row in rows]) if proposed else None,
                median_overhead_ms=median([row.duration_ms - 100 for row in rows]),
                token_cost_usd=round(sum(row.token_cost_usd for row in rows), 6),
                repeatability=round(len(fingerprints) / len(scenario_conditions), 6),
            )
        )
    return summaries
