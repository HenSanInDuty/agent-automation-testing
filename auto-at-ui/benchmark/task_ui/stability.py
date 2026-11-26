"""Pure helpers for the agent_loop task-stability harness (no network, no filesystem writes).

`scripts/run_task_stability.py` does the HTTP work; everything that can be unit-tested lives here:
suite validation, run records, resumability keys, summary math and markdown rendering.

Definitions used by `summarise`:
- completed rate  = runs with state == "completed" / all runs.
- agreement rate  = runs whose assessment status equals the modal status / completed runs that
  carry a status (ties are broken alphabetically so the result is deterministic).
- expected match  = runs whose assessment status equals `expected_status` / all runs (a run that
  never completed counts as a miss).
- stable          = overall completed rate >= 0.9 and overall agreement rate >= 0.9.
"""

import json
import re
from collections import Counter
from pathlib import Path

SCHEMA_VERSION = "task-ui-v1"
ASSESSMENT_STATUSES = ("achieved", "not_achieved", "blocked", "inconclusive")
TERMINAL_STATES = frozenset({"completed", "unavailable", "cancelled"})
STABLE_THRESHOLD = 0.9
_TASK_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_TASK_KEYS = {"id", "path", "task", "expected_status"}


def validate_suite(data):
    """Return the task list of a decoded suite or raise ValueError naming the first problem."""
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"suite schema_version must be {SCHEMA_VERSION}")
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("suite needs a non-empty tasks list")
    seen = set()
    for index, task in enumerate(tasks):
        if not isinstance(task, dict) or set(task) != _TASK_KEYS:
            raise ValueError(f"task #{index} must have exactly the keys {sorted(_TASK_KEYS)}")
        if not isinstance(task["id"], str) or not _TASK_ID.fullmatch(task["id"]):
            raise ValueError(f"task #{index} has an invalid id")
        if task["id"] in seen:
            raise ValueError(f"duplicate task id {task['id']}")
        seen.add(task["id"])
        path = task["path"]
        if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
            raise ValueError(f"task {task['id']}: path must start with a single '/'")
        text = task["task"]
        if not isinstance(text, str) or not text.strip() or len(text) > 4_000:
            raise ValueError(f"task {task['id']}: task text must be 1..4000 characters")
        if text != text.strip():
            raise ValueError(f"task {task['id']}: task text has surrounding whitespace")
        if task["expected_status"] not in ASSESSMENT_STATUSES:
            raise ValueError(f"task {task['id']}: unknown expected_status")
    return tasks


def load_suite(path):
    return validate_suite(json.loads(Path(path).read_text(encoding="utf-8")))


def select_tasks(tasks, ids):
    """Keep suite order; an empty selection means every task."""
    if not ids:
        return list(tasks)
    known = {task["id"] for task in tasks}
    unknown = sorted(set(ids) - known)
    if unknown:
        raise ValueError(f"unknown task id(s): {', '.join(unknown)}")
    return [task for task in tasks if task["id"] in set(ids)]


def target_url(base_url, task):
    return base_url.rstrip("/") + task["path"]


def run_key(task_id, run):
    return (task_id, int(run))


def plan(tasks, repeat, recorded):
    """Pending (task, run) pairs, task-major, skipping keys already in `recorded`."""
    if repeat < 1:
        raise ValueError("repeat must be at least 1")
    return [(task, run) for task in tasks for run in range(1, repeat + 1)
            if run_key(task["id"], run) not in recorded]


def idempotency_key(batch_id, task_id, run):
    """Stable per (batch, task, run): a resumed submit returns the same session, never a second."""
    return f"task-stability:{batch_id}:{task_id}:{run}"


def run_record(task, run, session, duration_s, *, recorded_at):
    """One runs.jsonl line from an ExplorationResponse-shaped dict (state may be 'timeout')."""
    assessment = session.get("task_assessment") or {}
    return {
        "task_id": task["id"], "run": int(run), "session_id": session.get("id"),
        "state": session.get("state"), "safe_failure_reason": session.get("safe_failure_reason"),
        "assessment_status": assessment.get("status"), "stop_reason": assessment.get("stop_reason"),
        "assessment_source": assessment.get("source"), "facts": assessment.get("facts"),
        "expected_status": task["expected_status"], "duration_s": round(float(duration_s), 1),
        "recorded_at": recorded_at,
    }


def parse_runs(text):
    """Decode runs.jsonl text. A torn last line from an interrupted write is ignored."""
    runs = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict) and "task_id" in value and "run" in value:
            runs.append(value)
    return runs


def load_runs(path):
    path = Path(path)
    return parse_runs(path.read_text(encoding="utf-8")) if path.exists() else []


def recorded_keys(runs):
    return {run_key(item["task_id"], item["run"]) for item in runs}


def _rate(numerator, denominator):
    return None if denominator == 0 else round(numerator / denominator, 4)


def _task_stats(task, runs):
    completed = [item for item in runs if item.get("state") == "completed"]
    statuses = Counter(item["assessment_status"] for item in completed
                       if item.get("assessment_status"))
    modal = min(statuses.items(), key=lambda pair: (-pair[1], pair[0]))[0] if statuses else None
    reasons = Counter((item.get("safe_failure_reason") or item.get("state") or "unknown")
                      for item in runs if item.get("state") != "completed")
    return {
        "task_id": task["id"], "expected_status": task["expected_status"], "runs": len(runs),
        "completed": len(completed), "completed_rate": _rate(len(completed), len(runs)),
        "assessed": sum(statuses.values()), "modal_status": modal,
        "modal_count": statuses[modal] if modal else 0,
        "agreement_rate": _rate(statuses[modal] if modal else 0, sum(statuses.values())),
        "expected_match": sum(1 for item in runs
                              if item.get("assessment_status") == task["expected_status"]),
        "expected_match_rate": _rate(
            sum(1 for item in runs if item.get("assessment_status") == task["expected_status"]),
            len(runs)),
        "status_counts": dict(sorted(statuses.items())),
        "unavailable_reasons": dict(sorted(reasons.items())),
    }


def summarise(tasks, runs):
    """Per-task and overall statistics. Later duplicate (task, run) lines replace earlier ones."""
    latest = {}
    for item in runs:
        latest[run_key(item["task_id"], item["run"])] = item
    by_task = {task["id"]: [] for task in tasks}
    for (task_id, _), item in sorted(latest.items()):
        if task_id in by_task:
            by_task[task_id].append(item)
    per_task = [_task_stats(task, by_task[task["id"]]) for task in tasks]
    total = sum(item["runs"] for item in per_task)
    completed = sum(item["completed"] for item in per_task)
    assessed = sum(item["assessed"] for item in per_task)
    modal = sum(item["modal_count"] for item in per_task)
    matched = sum(item["expected_match"] for item in per_task)
    reasons = Counter()
    for item in per_task:
        reasons.update(item["unavailable_reasons"])
    overall = {
        "runs": total, "completed": completed, "completed_rate": _rate(completed, total),
        "agreement_rate": _rate(modal, assessed), "expected_match_rate": _rate(matched, total),
        "unavailable_reasons": dict(sorted(reasons.items())),
    }
    overall["stable"] = is_stable(overall)
    return {"schema_version": "task-ui-stability-v1", "overall": overall, "tasks": per_task}


def is_stable(overall):
    completed, agreement = overall["completed_rate"], overall["agreement_rate"]
    return (completed is not None and agreement is not None
            and completed >= STABLE_THRESHOLD and agreement >= STABLE_THRESHOLD)


def _percent(value):
    return "n/a" if value is None else f"{value * 100:.0f}%"


def render_markdown(summary):
    overall = summary["overall"]
    verdict = "STABLE" if overall["stable"] else "NOT STABLE"
    lines = [
        "# Task stability", "",
        f"Verdict: **{verdict}** (needs completed rate and agreement rate >= "
        f"{_percent(STABLE_THRESHOLD)})", "",
        f"Runs: {overall['runs']}, completed: {_percent(overall['completed_rate'])}, "
        f"agreement: {_percent(overall['agreement_rate'])}, "
        f"expected match: {_percent(overall['expected_match_rate'])}", "",
        "| Task | Expected | Runs | Completed | Agreement | Expected match | Statuses |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in summary["tasks"]:
        counts = ", ".join(f"{k}={v}" for k, v in item["status_counts"].items()) or "-"
        lines.append(
            f"| {item['task_id']} | {item['expected_status']} | {item['runs']} | "
            f"{_percent(item['completed_rate'])} | {_percent(item['agreement_rate'])} | "
            f"{_percent(item['expected_match_rate'])} | {counts} |")
    lines += ["", "## Runs that did not complete", ""]
    unavailable = [(item["task_id"], reason, count) for item in summary["tasks"]
                   for reason, count in item["unavailable_reasons"].items()]
    lines += ([f"- {task}: {reason} x{count}" for task, reason, count in unavailable]
              or ["- none"])
    return "\n".join(lines) + "\n"


def reset_command(container, port=7300):
    """`docker exec` argv that calls POST /__reset inside the fixture container."""
    return ["docker", "exec", container, "wget", "-q", "-O-", "--post-data=reset",
            f"http://127.0.0.1:{port}/__reset"]
