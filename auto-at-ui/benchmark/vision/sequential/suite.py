"""Measure the actual reservation service and an isolated Chromium policy prototype."""

import asyncio
import hashlib
import json
import math
import shutil
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / part) for part in
               ("tests", "apps/control-plane", "packages/contracts/src")]


async def reservation_benchmark():
    from test_codex_candidate_service import Fixture, parsed

    rows = []
    for repetition in range(20):
        for scenario in (
            "stable", "stale_before_reserve", "stale_after_reserve", "stale_after_model",
        ):
            fixture = Fixture([parsed("dom_click")])
            answers = iter({
                "stable": [True, True, True], "stale_before_reserve": [False],
                "stale_after_reserve": [True, False],
                "stale_after_model": [True, True, False],
            }[scenario])

            async def state(answers=answers):
                return next(answers)

            fixture.state = state
            outcome = await fixture.run()
            rows.append(dict(repetition=repetition, scenario=scenario, status=outcome.status,
                             reason=outcome.failure_reason, actual_exchanges=len(fixture.calls),
                             reported_calls=outcome.calls_used,
                             refresh_gate_allows=outcome.calls_used == 0))
    return rows


def main():
    if (not Path("/offline-evaluation").exists() or shutil.which("codex")
            or (ROOT / ".env").exists()):
        raise RuntimeError("Use the isolated offline image, never the configured application")
    reservations = asyncio.run(reservation_benchmark())
    process = subprocess.run([
        "node", "--import", "tsx", "src/fixtures/exploration-strategy-benchmark.ts",
    ], cwd=ROOT / "workers/playwright", text=True, capture_output=True, check=True, timeout=600)
    browser = json.loads(process.stdout)
    grouped = defaultdict(list)
    for row in browser["rows"]:
        grouped[row["policy"], row["scenario"]].append(row)
    aggregates = []
    for (policy, scenario), rows in sorted(grouped.items()):
        durations = sorted(row["durationMs"] for row in rows)
        aggregates.append(dict(
            policy=policy, scenario=scenario, trials=len(rows),
            correct=sum(row["correct"] for row in rows),
            completed=sum(row["complete"] for row in rows),
            forbidden_clicks=sum(row["forbiddenClicks"] for row in rows),
            duplicate_clicks=sum(row["duplicateClicks"] for row in rows),
            proposals=sum(row["proposals"] for row in rows),
            p50_ms=round(statistics.median(durations), 3),
            p95_ms=durations[math.ceil(len(durations) * .95) - 1],
        ))
    files = ["apps/control-plane/application/codex_candidates.py",
             "apps/control-plane/application/vision_trace_events.py",
             "workers/playwright/src/vision-checkpoints.ts",
             "workers/playwright/src/fixtures/exploration-strategy-benchmark.ts"]
    report = dict(
        measured_at=datetime.now(UTC).isoformat(),
        scope="Offline current-source reservation benchmark + browser policy microbenchmark",
        percentile_method={"p50": "arithmetic median", "p95": "nearest rank ceil(0.95*n)"},
        limitations=["No real Codex calls, model quality, quota or provider latency measurement",
                     "Checkpoint baseline uses production state checks, not full BFS",
                     "Prototype is benchmark-only, not integrated into Temporal, DB or bridge",
                     "Synthetic mutations; not the failed website or an uptime estimate"],
        source_sha256={
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files
        },
        reservation_rows=reservations, browser=browser, aggregates=aggregates,
    )
    Path("/tmp/sequential-benchmark.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(dict(reservation_trials=len(reservations), browser_trials=len(browser["rows"]),
                          aggregates=aggregates)), flush=True)
    # Baseline failures are observations. A prototype safety/task failure fails the experiment.
    return int(any(not row["correct"] for row in browser["rows"]
                   if row["policy"] == "sequential_target_prototype"))


if __name__ == "__main__":
    raise SystemExit(main())
