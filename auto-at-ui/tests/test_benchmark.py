import json
import subprocess
import sys
from pathlib import Path

import pytest
from benchmark.harness import calculate_metrics, run_experiments
from benchmark.models import BenchmarkManifest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmarks" / "manifest.v1.json"


@pytest.fixture()
def manifest() -> BenchmarkManifest:
    return BenchmarkManifest.model_validate_json(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_covers_controlled_faults_and_pinned_environment(
    manifest: BenchmarkManifest,
) -> None:
    assert manifest.repetitions == 3
    assert manifest.pins.browser == "chromium@playwright-1.50.1"
    assert {scenario.fault_type for scenario in manifest.scenarios} == {
        "locator",
        "dom",
        "text",
        "timing",
        "product",
        "environment",
        "flaky",
    }


def test_repeated_runs_are_identical_within_declared_tolerance(manifest: BenchmarkManifest) -> None:
    first = run_experiments(manifest)
    second = run_experiments(manifest)

    assert [row.model_dump() for row in first] == [row.model_dump() for row in second]
    assert len(first) == len(manifest.scenarios) * 4 * manifest.repetitions
    assert manifest.reproducibility_tolerance_ms == 0


def test_metrics_include_comparison_and_ablation_conditions(manifest: BenchmarkManifest) -> None:
    metrics = {
        metric.condition.value: metric for metric in calculate_metrics(run_experiments(manifest))
    }

    assert metrics["baseline"].classification_f1 is None
    assert metrics["single_agent_triage"].classification_f1 == 1.0
    assert metrics["multi_agent_triage_healing"].valid_healing_rate == pytest.approx(2 / 3)
    assert metrics["multi_agent_triage_healing"].false_healing_rate == pytest.approx(1 / 3)
    assert metrics["selected_evidence_ablation"].classification_f1 < 1.0
    assert all(metric.repeatability == 1.0 for metric in metrics.values())


def test_export_script_writes_anonymised_chart_ready_result() -> None:
    output = ROOT / "benchmarks" / "exports" / "results.test.json"
    try:
        subprocess.run(
            [sys.executable, "scripts/run_benchmark.py", "--output", str(output)],
            cwd=ROOT,
            check=True,
        )

        exported = json.loads(output.read_text(encoding="utf-8"))
        assert exported["contract_version"] == "v1"
        assert len(exported["results"]) == 84
        encoded = json.dumps(exported)
        assert "not-a-secret-fixture" not in encoded
        assert "benchmark://" in encoded
    finally:
        output.unlink(missing_ok=True)
