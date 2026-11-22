"""Run the benchmark without credentials, network access, or application mounts."""

import argparse
import json
import subprocess
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
IMAGE = "auto-at-codex-offline:playwright-1.50.1"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()
    if not args.skip_build:
        subprocess.run(["docker", "build", "-t", IMAGE, "-f",
                        "benchmark/vision/codex/Dockerfile", "."], cwd=ROOT, check=True)
    name = f"auto-at-sequential-bench-{uuid4().hex[:12]}"
    output = ROOT / "benchmark/vision/sequential/results-20261105.json"
    try:
        result = subprocess.run([
            "docker", "run", "--name", name, "--init", "--network", "none",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "512",
            "--memory", "3g", "--shm-size", "512m", "--entrypoint", "uv", IMAGE,
            "run", "--no-sync", "python", "benchmark/vision/sequential/suite.py",
        ], cwd=ROOT)
        copied = subprocess.run(["docker", "cp", f"{name}:/tmp/sequential-benchmark.json",
                                 str(output)], capture_output=True)
        print(json.dumps({"result": str(output) if copied.returncode == 0 else None,
                          "exit_code": result.returncode}))
        return result.returncode or copied.returncode
    finally:
        subprocess.run(["docker", "rm", "--force", name], capture_output=True)


if __name__ == "__main__":
    raise SystemExit(main())
