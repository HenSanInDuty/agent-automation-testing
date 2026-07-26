"""Run the controlled thesis benchmark and export anonymised, chart-ready JSON."""

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "apps" / "control-plane"))
sys.path.insert(0, str(REPOSITORY_ROOT / "packages" / "contracts" / "src"))

from benchmark.harness import calculate_metrics, run_experiments  # noqa: E402
from benchmark.models import BenchmarkManifest  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("benchmarks/manifest.v1.json"))
    parser.add_argument("--output", type=Path, default=Path("benchmarks/exports/results.v1.json"))
    arguments = parser.parse_args()
    manifest = BenchmarkManifest.model_validate_json(arguments.manifest.read_text(encoding="utf-8"))
    results = run_experiments(manifest)
    payload = {
        "contract_version": "v1",
        "manifest_id": manifest.id,
        "pins": manifest.pins.model_dump(mode="json"),
        "results": [result.model_dump(mode="json") for result in results],
        "metrics": [summary.model_dump(mode="json") for summary in calculate_metrics(results)],
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
