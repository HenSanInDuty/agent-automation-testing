"""Measure run-to-run stability of the agent_loop task-testing engine (ADR-046). Operator tool.

    uv run python scripts/run_task_stability.py prepare --project <name-or-id> \
        --origin http://task-target:7300
    uv run python scripts/run_task_stability.py run --project <name-or-id> \
        --base-url http://task-target:7300 --repeat 5 --out .pytest-artifacts/task-stability/r1
    uv run python scripts/run_task_stability.py report --out .pytest-artifacts/task-stability/r1

`run` submits real agent_loop sessions (each one calls the configured model bridge) one at a time,
polls them in this one process and appends one line per finished run to `<out>/runs.jsonl`.
Re-running the same command resumes: recorded (task, run) pairs are skipped and a half-finished
submit is re-attached through its deterministic idempotency key. Auth headers come from a private
JSON file (default as in benchmark/vision/accuracy/round_v4.py) and are never printed.
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "contracts" / "src"))
sys.path.insert(0, str(ROOT / "benchmark" / "task_ui"))

import stability  # noqa: E402
from auto_at.contracts.generation import canonical_origin  # noqa: E402

DEFAULT_API = "http://127.0.0.1:7000"
DEFAULT_HEADERS = ROOT / ".pytest-artifacts" / "accuracy-local-headers.json"
DEFAULT_SUITE = ROOT / "benchmarks" / "task-ui" / "tasks.v1.json"
DEFAULT_CONTAINER = "auto-at-ui-task-target-1"
MIN_POLL_SECONDS = 5.0


def client(api, headers_file):
    headers = json.loads(Path(headers_file).read_text(encoding="utf-8"))
    return httpx.Client(base_url=api, headers=headers, timeout=30)


def find_project(api, project):
    try:
        return str(UUID(project))
    except ValueError:
        pass
    response = api.get("/api/v1/projects", params={"q": project})
    response.raise_for_status()
    exact = [item for item in response.json() if item["name"] == project]
    if len(exact) != 1:
        raise SystemExit(f"project name {project!r} matched {len(exact)} projects; pass its id")
    return exact[0]["id"]


def policy_path(project_id):
    return f"/api/v1/test-generations/projects/{project_id}/policy"


def prepare(args):
    origin = canonical_origin(args.origin)
    with client(args.api, args.headers_file) as api:
        project_id = find_project(api, args.project)
        current = api.get(policy_path(project_id))
        current.raise_for_status()
        current = current.json()
        others = [item for item in current["allowed_origins"] if item != origin]
        origins = [origin] if args.replace_origins else [*others, origin]
        if others and not args.replace_origins:
            print(f"warning: project also allows {others}; vision_owned_test_target applies to "
                  "every allowed origin. Use --replace-origins or a dedicated project.",
                  file=sys.stderr)
        body = {"allowed_origins": origins, "vision_max_hops": current["vision_max_hops"],
                "vision_max_states": current["vision_max_states"],
                "vision_owned_test_target": True}
        response = api.put(policy_path(project_id), json=body)
        response.raise_for_status()
        print(json.dumps({"project_id": project_id, **response.json()}, indent=2))
    return 0


def submit(api, project_id, url, task_text, key):
    policy = api.get("/api/v1/vision/policy")
    policy.raise_for_status()
    policy = policy.json()
    if not policy.get("agent_loop_enabled"):
        raise SystemExit("agent_loop is disabled on the control plane "
                         "(VISION_AGENT_LOOP_ENABLED); start the agent-loop compose overlay")
    body = {"project_id": project_id, "target_url": url, "task_intent": task_text,
            "use_vision": True, "engine": "agent_loop",
            "expected_provider": policy["provider"], "expected_model": policy["model"],
            "expected_input_policy_fingerprint": policy["input_policy_fingerprint"]}
    response = api.post("/api/v1/vision/explorations", json=body,
                        headers={"Idempotency-Key": key})
    if response.status_code >= 400:
        raise SystemExit(f"submit failed: HTTP {response.status_code} {response.text[:300]}")
    return response.json()


def wait_terminal(api, session_id, *, poll, timeout, sleep=time.sleep, clock=time.monotonic):
    """Poll one session. Returns (session, True) when terminal, (last session, False) on timeout."""
    deadline = clock() + timeout
    failures = 0
    session = {"id": session_id, "state": "unknown"}
    while True:
        try:
            response = api.get(f"/api/v1/vision/explorations/{session_id}")
            response.raise_for_status()
            session, failures = response.json(), 0
            if session["state"] in stability.TERMINAL_STATES:
                return session, True
        except httpx.HTTPError as error:
            failures += 1
            if failures >= 3:
                raise SystemExit(f"polling {session_id} failed 3 times: {error!r}") from error
        if clock() >= deadline:
            return session, False
        sleep(poll)


def reset_target(container):
    subprocess.run(stability.reset_command(container), check=True, capture_output=True,
                   timeout=60, stdin=subprocess.DEVNULL)


def append(path, record):
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        stream.flush()


def run(args):
    tasks = stability.select_tasks(stability.load_suite(args.suite), args.task)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    batch_file = out / "batch.json"
    if batch_file.exists():
        batch = json.loads(batch_file.read_text(encoding="utf-8"))["batch_id"]
    else:
        batch = uuid4().hex
        batch_file.write_text(json.dumps({"batch_id": batch, "base_url": args.base_url}) + "\n",
                              encoding="utf-8", newline="\n")
    runs_file = out / "runs.jsonl"
    pending = stability.plan(tasks, args.repeat, stability.recorded_keys(
        stability.load_runs(runs_file)))
    print(f"{len(pending)} run(s) pending, batch {batch}", flush=True)
    with client(args.api, args.headers_file) as api:
        project_id = find_project(api, args.project)
        for task, number in pending:
            if not args.no_reset:
                reset_target(args.reset_container)
            started = time.monotonic()
            created = submit(api, project_id, stability.target_url(args.base_url, task),
                             task["task"], stability.idempotency_key(batch, task["id"], number))
            session, done = wait_terminal(api, created["id"], poll=args.poll,
                                          timeout=args.session_timeout)
            if not done:
                session = {**session, "state": "timeout", "safe_failure_reason": "harness_timeout"}
            record = stability.run_record(task, number, session, time.monotonic() - started,
                                          recorded_at=datetime.now(UTC).isoformat())
            append(runs_file, record)
            # A run without an assessment names why it has none (the failure reason).
            outcome = (record["assessment_status"] or record.get("safe_failure_reason")
                       or "no reason")
            print(f"{task['id']} #{number}: {record['state']} {outcome} "
                  f"({record['duration_s']}s)", flush=True)
    return 0


def report(args):
    out = Path(args.out)
    runs = stability.load_runs(out / "runs.jsonl")
    # A partial run (`--task`) is judged only on the tasks it actually ran.
    recorded = {item["task_id"] for item in runs}
    tasks = [item for item in stability.load_suite(args.suite) if item["id"] in recorded]
    summary = stability.summarise(tasks, runs)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                                      encoding="utf-8", newline="\n")
    markdown = stability.render_markdown(summary)
    (out / "summary.md").write_text(markdown, encoding="utf-8", newline="\n")
    print(markdown)
    print("STABLE" if summary["overall"]["stable"] else "NOT STABLE")
    return 0


def poll_seconds(value):
    number = float(value)
    if number < MIN_POLL_SECONDS:
        raise argparse.ArgumentTypeError(f"must be at least {MIN_POLL_SECONDS:g} seconds")
    return number


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--headers-file", type=Path, default=DEFAULT_HEADERS,
                        help="Private JSON auth headers; never printed")
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    commands = parser.add_subparsers(dest="command", required=True)

    prep = commands.add_parser("prepare", help="allow the origin and mark the project as owned")
    prep.add_argument("--project", required=True)
    prep.add_argument("--origin", required=True)
    prep.add_argument("--replace-origins", action="store_true",
                      help="allow only --origin instead of adding it to the existing list")
    prep.set_defaults(handler=prepare)

    runner = commands.add_parser("run", help="submit tasks x repeat and record each result")
    runner.add_argument("--project", required=True)
    runner.add_argument("--base-url", required=True)
    runner.add_argument("--repeat", type=positive_int, default=3)
    runner.add_argument("--task", action="append", default=[], help="task id; repeatable")
    runner.add_argument("--out", type=Path, required=True)
    runner.add_argument("--poll", type=poll_seconds, default=MIN_POLL_SECONDS)
    runner.add_argument("--session-timeout", type=positive_int, default=900,
                        help="seconds to wait for one session before recording a timeout")
    runner.add_argument("--no-reset", action="store_true",
                        help="do not POST /__reset on the fixture before each run")
    runner.add_argument("--reset-container", default=DEFAULT_CONTAINER)
    runner.set_defaults(handler=run)

    rep = commands.add_parser("report", help="write summary.json and summary.md")
    rep.add_argument("--out", type=Path, required=True)
    rep.set_defaults(handler=report)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
