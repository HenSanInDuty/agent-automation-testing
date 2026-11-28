"""ADR-047 phase 16: end-to-end run on the task-ui fixture, real stack and model. Operator tool.

Every step resumes from `<out>/state.json`, appends one JSON line per fact to `<out>/events.jsonl`,
and never prints or stores a typed value (only lengths, ids, statuses and error codes). Steps are
short on purpose (one shell call must stay under ~9 minutes):

    uv run python scripts/run_agent_task_draft_e2e.py --out <dir> setup
    ... sessions --name pos-login --name pos-todo ...      (each one real agent_loop session)
    ... positive --name pos-login                          (draft -> approve -> first run)
    ... reruns --name pos-login --count 5                  (POST /__reset, then run again)
    ... case a|bj|c|d|e|f|g|h|i                            (negative cases, see CASES)
    ... scan --name pos-login --marker marker-todo         (DB tables, logs, trace artifacts)
    ... summary
    ... teardown                                           (remove the second fixture container)

Two actors with different `X-Actor-Id` and roles: the requester (contributor) and the reviewer.
Sessions and project setup use the private admin header file, as in `run_task_stability.py`.
"""

import argparse
import json
import subprocess
import sys
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "contracts" / "src"))
sys.path.insert(0, str(ROOT / "benchmark" / "task_ui"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_task_stability as rts  # noqa: E402
import stability  # noqa: E402

TENANT = "demo-tenant"
REQUESTER = {"X-Tenant-Id": TENANT, "X-Actor-Id": "task-e2e-requester",
             "X-Actor-Roles": "contributor"}
REVIEWER = {"X-Tenant-Id": TENANT, "X-Actor-Id": "task-e2e-reviewer", "X-Actor-Roles": "reviewer"}
SAME_PERSON = {**REQUESTER, "X-Actor-Roles": "contributor,reviewer"}
POSTGRES = "auto-at-ui-postgres-1"
FIXTURE_PROJECT = "Task UI fixture"
E2E_PROJECT = "Task UI e2e"
PASSWORD_PROJECT = "Task UI e2e password label"
HEALTHY_BASE = "http://task-target:7300"
E2E_BASE = "http://task-target-e2e:7300"
E2E_CONTAINER = "auto-at-ui-task-target-e2e"
HEALTHY_CONTAINER = rts.DEFAULT_CONTAINER
NETWORK = "auto-at-ui_default"
IMAGE = "auto-at-ui-task-target"
LOG_CONTAINERS = ("auto-at-ui-control-plane-1", "auto-at-ui-temporal-worker-1",
                  "auto-at-ui-playwright-worker-1", "auto-at-ui-claude-bridge-1")
TERMINAL_RUN = frozenset({"passed", "failed", "errored", "skipped", "cancelled"})

# Where a typed value may be stored, as (table, column) of the control-plane database (ADR-047
# "Giá trị test (Q1)" places 1-4; the others are outside the database). A new place is a decision
# for the PM and a new entry here, never a quiet exception: tests/test_agent_task_draft_e2e.py pins
# these sets and fails when the scan finds a value anywhere else.
DECLARED_AFTER_CREATE = frozenset({("generated_test_drafts", "playwright_test_source")})
DECLARED_AFTER_APPROVAL = DECLARED_AFTER_CREATE | {
    ("test_cases", "specification"),
    ("test_runs", "request"),
    ("outbox_events", "payload"),
}
# Never allowed to hold a value (criterion 4). Reported one by one; any hit is an ESCALATE.
MUST_BE_CLEAN_TABLES = (
    "visual_exploration_sessions", "visual_agent_steps", "audit_events", "generation_requests",
)
# Free text the model writes about a session. When the author's own task text contains the value
# (demo account, keyword) the model copies it here; ADR-047 (phase 15c) accepts that as a usage
# condition, so these columns are reported apart for such values. A value only the requester typed
# when asking for the draft (the marker) must not reach them, and the other tables stay clean.
FREE_TEXT_PLACES = frozenset({
    ("visual_exploration_sessions", "task_assessment"), ("visual_agent_steps", "memory"),
    ("visual_agent_steps", "evaluation_previous_goal"), ("visual_agent_steps", "next_goal"),
})
VALUE_IN_TASK_TEXT = frozenset({"pos-login", "pos-todo", "pos-search"})
# Artifact members a value is expected in (phase 07 spike, runner-r1.md section 3; phase 16 r1 and
# ADR-047 place 9, phase 15c): the trace events (`*.trace`), the copy of the source
# (`resources/src@*.txt`) and the DOM snapshots (`resources/*.html`); when the page sends a request
# (login, add a todo) also the network log (`0-trace.network`, `postData`) and the request bodies
# (`resources/<sha1>.dat`); `playwright-output` only when the run failed near the typed line
# (place 10). Anything else (`0-trace.stacks`, logs) is an ESCALATE.
ARTIFACT_PLACES_EXPECTED = (".trace", "resources/src@", ".html", "0-trace.network", ".dat")
ARTIFACT_PLACES_ON_FAILURE = ("playwright-output",)

# Task text each session is asked, taken from the suite so the two never drift.
SESSIONS = {
    "pos-login": {"project": FIXTURE_PROJECT, "task": "login-success", "base": HEALTHY_BASE},
    "pos-todo": {"project": FIXTURE_PROJECT, "task": "todo-add", "base": HEALTHY_BASE},
    "pos-search": {"project": FIXTURE_PROJECT, "task": "search-results", "base": HEALTHY_BASE},
    "marker-todo": {"project": FIXTURE_PROJECT, "task": "todo-add", "base": HEALTHY_BASE},
    "neg-a-save": {"project": FIXTURE_PROJECT, "task": "broken-save", "base": HEALTHY_BASE},
    "neg-a-counter": {"project": FIXTURE_PROJECT, "task": "broken-counter", "base": HEALTHY_BASE},
    "e2e-0": {"project": E2E_PROJECT, "task": "login-success", "base": E2E_BASE},
    "e2e-1": {"project": E2E_PROJECT, "task": "login-success", "base": E2E_BASE},
    "e2e-2": {"project": E2E_PROJECT, "task": "login-success", "base": E2E_BASE},
    "e2e-c": {"project": E2E_PROJECT, "task": "login-success", "base": E2E_BASE},
    "e2e-broken": {"project": E2E_PROJECT, "task": "login-success", "base": E2E_BASE,
                   "mode": {"broken": 1}},
    "pw-label": {"project": PASSWORD_PROJECT, "task": "login-success", "base": E2E_BASE,
                 "mode": {"pw": 1}},
}
# Values each session's typed steps take, in order (a lengths mismatch is reported, never forced).
MARKER = "ZQ4471-todo1"  # 12 characters, the length of the todo text typed by the agent
VALUES = {
    "pos-login": ["demo", "Demo1234"], "e2e-0": ["demo", "Demo1234"],
    "e2e-1": ["demo", "Demo1234"], "e2e-c": ["demo", "Demo1234"], "e2e-2": ["demo", "Demo1234"],
    "pw-label": ["demo", "Demo1234"],
    "pos-todo": ["Viết báo cáo"], "pos-search": ["balo"], "marker-todo": [MARKER],
}
SCAN_VALUES = {"pos-login": ["Demo1234"], "pos-todo": ["Viết báo cáo"],
               "pos-search": ["balo"], "marker-todo": [MARKER]}


# ----------------------------------------------------------------------------- pure helpers


def needle_variants(value):
    """The spellings a value can take in a JSON dump, a JS string literal or a JSON-in-JSON text."""
    ascii_escaped = json.dumps(value)[1:-1]
    variants = [value, ascii_escaped, ascii_escaped.replace("\\", "\\\\")]
    return list(dict.fromkeys(variants))


def values_for(name, type_steps):
    """The values for the typed steps `type_steps` reported, or None on a length mismatch."""
    pool = VALUES.get(name, [])
    if len(pool) != len(type_steps) or any(
            len(value) != step["text_chars"] for value, step in zip(pool, type_steps, strict=True)):
        return None
    return list(pool)


def unexpected_places(found, declared):
    """Places a value was found that are not declared (sorted, deterministic)."""
    return sorted(set(found) - set(declared))


def clean_table_hits(places, name):
    """Tables that must stay clean but hold the value; free text counts only for a marker value."""
    allowed = FREE_TEXT_PLACES if name in VALUE_IN_TASK_TEXT else frozenset()
    return sorted({t for t, c in places if t in MUST_BE_CLEAN_TABLES and (t, c) not in allowed})


def free_text_hits(places, name):
    """Free-text columns that hold a value the task text contained (accepted, reported)."""
    return sorted(f"{t}.{c}" for t, c in places if (t, c) in FREE_TEXT_PLACES
                  and name in VALUE_IN_TASK_TEXT)


def missing_places(found, declared):
    return sorted(set(declared) - set(found))


def artifact_verdict(hits):
    """`hits`: {relative member path: needle count} -> (expected, on_failure_only, unexpected)."""
    expected = sorted(path for path in hits if any(key in path for key in ARTIFACT_PLACES_EXPECTED))
    on_failure = sorted(path for path in hits if path not in expected
                        and any(key in path for key in ARTIFACT_PLACES_ON_FAILURE))
    unexpected = sorted(set(hits) - set(expected) - set(on_failure))
    return expected, on_failure, unexpected


def files_containing(root, variants):
    """Relative paths under `root` whose bytes contain any spelling of the value (`grep -rlaF`)."""
    patterns = [item.encode("utf-8") for item in variants]
    found = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_file():
            data = path.read_bytes()
            count = sum(data.count(pattern) for pattern in patterns)
            if count:
                found[path.relative_to(root).as_posix()] = count
    return found


def patch_fixture_source(text):
    """Server source for the second fixture container: the repo file plus a `POST /__mode` switch.

    `broken=1` changes the greeting that the login success page shows; `pw=1` labels the password
    field "Password". The repo's `server.mjs` stays untouched; a missing anchor is a hard error so a
    changed fixture cannot silently produce an unbroken "broken" copy.
    """
    edits = (
        ('const ACCOUNT = { username: "demo", password: "Demo1234" };',
         'const ACCOUNT = { username: "demo", password: "Demo1234" };\n'
         "const mode = { broken: false, pw: false };"),
        ('<p role="status">Xin chào, ${esc(user)}</p>',
         '<p role="status">${mode.broken ? "Chào mừng trở lại" : "Xin chào"}, ${esc(user)}</p>'),
        ('<label for="password">Mật khẩu</label>',
         '<label for="password">${mode.pw ? "Password" : "Mật khẩu"}</label>'),
        ('    case "GET /healthz":',
         '    case "POST /__mode":\n'
         '      mode.broken = url.searchParams.get("broken") === "1";\n'
         '      mode.pw = url.searchParams.get("pw") === "1";\n'
         '      response.writeHead(200, { "content-type": "application/json" });\n'
         "      return response.end(JSON.stringify(mode));\n"
         '    case "GET /healthz":'),
    )
    for old, new in edits:
        if text.count(old) != 1:
            raise ValueError(f"fixture anchor not found exactly once: {old[:40]!r}")
        text = text.replace(old, new)
    return text


def mode_command(container, broken=0, pw=0, port=7300):
    return ["docker", "exec", container, "wget", "-q", "-O-", "--post-data=x",
            f"http://127.0.0.1:{port}/__mode?broken={int(broken)}&pw={int(pw)}"]


# ----------------------------------------------------------------------------- state and output


class Run:
    def __init__(self, args):
        self.out = Path(args.out).resolve()
        self.out.mkdir(parents=True, exist_ok=True)
        self.state_file = self.out / "state.json"
        self.state = (json.loads(self.state_file.read_text("utf-8")) if self.state_file.exists()
                      else {"batch": uuid4().hex, "projects": {}, "sessions": {}, "drafts": {},
                            "runs": {}, "cases": {}})
        self.admin_headers = json.loads(Path(args.headers_file).read_text("utf-8"))
        self.api_url = args.api
        self.suite = {item["id"]: item for item in stability.load_suite(args.suite)}

    def save(self):
        self.state_file.write_text(json.dumps(self.state, indent=2, ensure_ascii=False) + "\n",
                                   encoding="utf-8", newline="\n")

    def client(self, headers):
        return httpx.Client(base_url=self.api_url, headers=headers, timeout=60)

    def emit(self, kind, **data):
        record = {"at": datetime.now(UTC).isoformat(), "kind": kind, **data}
        rts.append(self.out / "events.jsonl", record)
        print(json.dumps(record, ensure_ascii=False), flush=True)


def docker(*args, input_bytes=None, timeout=120):
    return subprocess.run(["docker", *args], capture_output=True, timeout=timeout, check=False,
                          input=input_bytes if input_bytes is not None else b"",
                          cwd=ROOT)


def psql(sql):
    result = docker("exec", "-i", POSTGRES, "psql", "-U", "auto_at", "-d", "auto_at", "-At",
                    "-F", "|", "-f", "-", input_bytes=sql.encode("utf-8"), timeout=180)
    if result.returncode != 0:
        raise SystemExit(f"psql failed: {result.stderr.decode('utf-8', 'replace')[:300]}")
    return [line for line in result.stdout.decode("utf-8").splitlines() if line]


def error_code(response):
    try:
        detail = response.json().get("detail")
    except ValueError:
        return None
    if isinstance(detail, dict):
        return detail.get("code")
    return detail if isinstance(detail, str) else None


def check(run, case, label, response, status, code=None):
    """Record one expectation: HTTP status and error code. Never the body."""
    actual_code = error_code(response) if response.status_code >= 400 else None
    ok = response.status_code == status and (code is None or actual_code == code)
    run.emit("check", case=case, label=label, expected_status=status, expected_code=code,
             status=response.status_code, code=actual_code, ok=ok)
    return ok


# ----------------------------------------------------------------------------- setup / fixture


def project_id(run, admin, name):
    return rts.find_project(admin, name)


def ensure_project(run, admin, name, origins):
    found = admin.get("/api/v1/projects", params={"q": name}).json()
    exact = [item for item in found if item["name"] == name]
    if exact:
        pid = exact[0]["id"]
    else:
        created = admin.post("/api/v1/projects", json={"name": name, "default_target": "web_ui"})
        created.raise_for_status()
        pid = created.json()["id"]
    current = admin.get(rts.policy_path(pid)).json()
    body = {"allowed_origins": origins, "vision_max_hops": current["vision_max_hops"],
            "vision_max_states": current["vision_max_states"], "vision_owned_test_target": True}
    admin.put(rts.policy_path(pid), json=body).raise_for_status()
    return pid


def set_flag(admin, pid, enabled):
    current = admin.get(rts.policy_path(pid)).json()
    body = {"allowed_origins": current["allowed_origins"],
            "vision_max_hops": current["vision_max_hops"],
            "vision_max_states": current["vision_max_states"],
            "vision_owned_test_target": enabled}
    admin.put(rts.policy_path(pid), json=body).raise_for_status()


def cmd_setup(run, args):
    original = (ROOT / "benchmarks/targets/task-ui/server.mjs").read_text("utf-8")
    server = patch_fixture_source(original)
    patched = run.out / "server-e2e.mjs"
    patched.write_text(server, encoding="utf-8", newline="\n")
    existing = docker("ps", "-a", "--filter", f"name=^{E2E_CONTAINER}$", "--format", "{{.Names}}")
    if E2E_CONTAINER not in existing.stdout.decode():
        for step in (
            ("create", "--name", E2E_CONTAINER, "--network", NETWORK,
             "--network-alias", "task-target-e2e", IMAGE),
            ("cp", str(patched.relative_to(ROOT)).replace("\\", "/"),
             f"{E2E_CONTAINER}:/benchmark/server.mjs"),
            ("start", E2E_CONTAINER),
        ):
            result = docker(*step)
            if result.returncode != 0:
                raise SystemExit(f"docker {step[0]} failed: {result.stderr.decode()[:300]}")
        time.sleep(3)
    with run.client(run.admin_headers) as admin:
        fixture_pid = rts.find_project(admin, FIXTURE_PROJECT)
        run.state["projects"][FIXTURE_PROJECT] = fixture_pid
        for name in (E2E_PROJECT, PASSWORD_PROJECT):
            run.state["projects"][name] = ensure_project(run, admin, name, [E2E_BASE])
        policy = admin.get("/api/v1/vision/policy").json()
        meta = {"provider": policy["provider"], "model": policy["model"],
                "agent_loop_enabled": policy.get("agent_loop_enabled")}
        flag = admin.get(rts.policy_path(fixture_pid)).json()["vision_owned_test_target"]
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, cwd=ROOT,
                          check=True).stdout.decode().strip()
    run.state["meta"] = meta | {"head": head, "fixture_flag": flag}
    run.save()
    reset_all()
    run.emit("setup", projects=run.state["projects"], meta=run.state["meta"])
    return 0


def reset_all():
    for container in (HEALTHY_CONTAINER, E2E_CONTAINER):
        rts.reset_target(container)
    docker("exec", E2E_CONTAINER, "wget", "-q", "-O-", "--post-data=x",
           "http://127.0.0.1:7300/__mode?broken=0&pw=0")


def cmd_teardown(run, args):
    docker("rm", "-f", E2E_CONTAINER)
    run.emit("teardown", container=E2E_CONTAINER)
    return 0


# ----------------------------------------------------------------------------- sessions


def container_for(base):
    return E2E_CONTAINER if base == E2E_BASE else HEALTHY_CONTAINER


def model_calls(session_id):
    rows = psql(f"select count(*) from visual_agent_steps where session_id = '{session_id}';")
    return int(rows[0])


def cmd_sessions(run, args):
    for name in args.name:
        plan = SESSIONS[name]
        if name in run.state["sessions"] and not args.again:
            run.emit("session_skipped", name=name)
            continue
        if name in run.state["sessions"]:  # --again: keep the earlier attempt for the rates
            run.state.setdefault("history", {}).setdefault(name, []).append(
                run.state["sessions"][name])
        task = run.suite[plan["task"]]
        container = container_for(plan["base"])
        rts.reset_target(container)
        mode = plan.get("mode", {})
        if container == E2E_CONTAINER:
            subprocess.run(mode_command(container, **mode), check=True, capture_output=True,
                           timeout=60, stdin=subprocess.DEVNULL)
        started = time.monotonic()
        try:
            with run.client(run.admin_headers) as admin:
                created = rts.submit(admin, run.state["projects"][plan["project"]],
                                     stability.target_url(plan["base"], task), task["task"],
                                     f"task-e2e:{run.state['batch']}:{name}:{uuid4().hex[:6]}")
                session, done = rts.wait_terminal(admin, created["id"], poll=5, timeout=400)
        finally:
            if container == E2E_CONTAINER:
                subprocess.run(mode_command(container), check=False, capture_output=True,
                               timeout=60, stdin=subprocess.DEVNULL)
        assessment = session.get("task_assessment") or {}
        items = (assessment.get("verified_text") or {}).get("items") or []
        record = {"id": session["id"], "state": session["state"] if done else "timeout",
                  "safe_failure_reason": session.get("safe_failure_reason"),
                  "status": assessment.get("status"), "candidates": len(items),
                  "model_calls": model_calls(session["id"]) if done else None,
                  "seconds": round(time.monotonic() - started, 1), "task": plan["task"],
                  "expected": task["expected_status"], "project": plan["project"]}
        run.state["sessions"][name] = record
        run.save()
        run.emit("session", name=name, **record)
    return 0


# ----------------------------------------------------------------------------- draft flow


def wait_run(client, run_id, timeout=150, poll=3):
    deadline = time.monotonic() + timeout
    body = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/runs/{run_id}")
        if response.status_code == 200:
            body = response.json()
            if body["status"] in TERMINAL_RUN:
                return body
        time.sleep(poll)
    return {**body, "status": body.get("status", "unknown") + "-timeout"}


def inputs_of(requester, session_id):
    response = requester.get(f"/api/v1/vision/explorations/{session_id}/test-draft/inputs")
    return response, (response.json() if response.status_code == 200 else {})


def post_draft(requester, session_id, values, key=None):
    return requester.post(f"/api/v1/vision/explorations/{session_id}/test-draft",
                          json={"values": values},
                          headers={"Idempotency-Key": key or uuid4().hex})


def approve(reviewer, draft_id, ack=True, approved=True):
    return reviewer.post(f"/api/v1/test-generations/drafts/{draft_id}/decision",
                         json={"approved": approved, "acknowledge_disposable_credentials": ack})


def create_and_approve(run, name, requester, reviewer, label, broken=False):
    """Criterion 1 and 4b for one session. Returns the stored draft record or None."""
    session = run.state["sessions"][name]
    response, inputs = inputs_of(requester, session["id"])
    steps = inputs.get("type_steps", [])
    run.emit("inputs", name=name, status=response.status_code,
             owned=inputs.get("owned_test_target"),
             has_type_steps=inputs.get("has_type_steps"),
             lengths=[step["text_chars"] for step in steps])
    values = values_for(name, steps)
    if values is None:
        run.emit("values_mismatch", name=name,
                 expected_lengths=[len(v) for v in VALUES.get(name, [])],
                 lengths=[step["text_chars"] for step in steps])
        return None
    key = f"e2e-{run.state['batch']}-{name}-{session['id'][:8]}"
    created = post_draft(requester, session["id"], values, key)
    ok = check(run, label, "request draft (requester)", created, 201)
    if not ok:
        return None
    body = created.json()
    # The approval starts the first run at once: the fixture must be in its initial state first.
    rts.reset_target(E2E_CONTAINER if session["project"] != FIXTURE_PROJECT else HEALTHY_CONTAINER)
    if broken:
        set_mode(broken=1)
    decision = approve(reviewer, body["draft_id"])
    check(run, label, "approve (reviewer, ack)", decision, 200)
    if decision.status_code != 200:
        return None
    draft = decision.json()
    return {"draft_id": body["draft_id"], "request_id": body["request_id"],
            "source_hash": body["source_hash"], "state": draft["state"],
            "test_case_id": draft["linked_test_case_id"], "run_id": draft["linked_run_id"],
            "project": session["project"]}


def cmd_positive(run, args):
    for name in args.name:
        with run.client(REQUESTER) as requester, run.client(REVIEWER) as reviewer:
            if name in run.state["drafts"]:
                run.emit("positive_skipped", name=name)
                continue
            record = create_and_approve(run, name, requester, reviewer, f"positive:{name}")
            if record is None:
                continue
            result = wait_run(requester, record["run_id"])
            record["first_run"] = {"run_id": record["run_id"], "status": result["status"],
                                   "target_url": result.get("target_url")}
            run.state["drafts"][name] = record
            run.state["runs"].setdefault(name, []).append(
                {"run_id": record["run_id"], "status": result["status"], "kind": "first"})
            run.save()
            run.emit("positive", name=name, **{k: v for k, v in record.items()
                                                 if k != "first_run"}, run_status=result["status"])
    return 0


def api_rerun(run, client, first_run_id):
    """Run the approved test once more through `POST /api/v1/runs` (the dashboard's path).

    The body is the stored first-run request minus the ids the route assigns; the route adds its own
    `traceparent` (phase 15c: the worker accepts it). Returns the terminal run.
    """
    rows = psql(f"select request::text from test_runs where id = '{first_run_id}';")
    request = json.loads(rows[0])
    config = {k: v for k, v in request["runner_config"].items() if k != "traceparent"}
    body = {"project_id": request["project_id"], "test_case_id": request["test_case_id"],
            "target_type": request["target_type"], "target_url": request["target_url"],
            "runner_config": config, "artifact_policy": request["artifact_policy"]}
    created = client.post("/api/v1/runs", json=body, headers={"Idempotency-Key": uuid4().hex})
    if created.status_code != 201:
        return {"run_id": None, "status": f"create-{created.status_code}",
                "summary": error_code(created)}
    result = wait_run(client, created.json()["id"])
    return {"run_id": created.json()["id"], "status": result["status"],
            "summary": result.get("terminal_summary")}


def cmd_reruns(run, args):
    for name in args.name:
        record = run.state["drafts"][name]
        base = HEALTHY_BASE if record["project"] == FIXTURE_PROJECT else E2E_BASE
        container = container_for(base)
        done = [item for item in run.state["runs"][name] if item["kind"] == "rerun"]
        for number in range(len(done) + 1, args.count + 1):
            rts.reset_target(container)
            with run.client(REQUESTER) as requester:
                result = api_rerun(run, requester, record["run_id"])
            run.state["runs"][name].append({"run_id": result["run_id"], "status": result["status"],
                                            "kind": "rerun", "via": "POST /api/v1/runs"})
            run.save()
            run.emit("rerun", name=name, number=number, run_id=result["run_id"],
                     status=result["status"], summary=result["summary"])
        statuses = [item["status"] for item in run.state["runs"][name] if item["kind"] == "rerun"]
        run.emit("rerun_summary", name=name, **stability.rerun_summary(statuses))
    return 0


# ----------------------------------------------------------------------------- negative cases


def set_mode(**mode):
    subprocess.run(mode_command(E2E_CONTAINER, **mode), check=True, capture_output=True,
                   timeout=60, stdin=subprocess.DEVNULL)


def case_a(run, requester, reviewer, admin):
    for name in ("neg-a-save", "neg-a-counter"):
        session = run.state["sessions"][name]
        check(run, "a", f"{name} status={session['status']}", post_draft(
            requester, session["id"], []), 409, "assessment_not_achieved")


def case_g(run, requester, reviewer, admin):
    session = run.state["sessions"]["e2e-0"]
    pid = run.state["projects"][E2E_PROJECT]
    set_flag(admin, pid, False)
    try:
        response, inputs = inputs_of(requester, session["id"])
        run.emit("inputs", name="e2e-0 flag off", status=response.status_code,
                 owned=inputs.get("owned_test_target"), lengths=[
                     step["text_chars"] for step in inputs.get("type_steps", [])])
        before = [item["draft_id"] for item in run.state["drafts"].values()]
        check(run, "g", "flag off + type steps", post_draft(
            requester, session["id"], VALUES["e2e-0"]), 409, "input_value_not_allowed")
        run.emit("g_no_draft", drafts_before=len(before))
    finally:
        set_flag(admin, pid, True)


def case_bj(run, requester, reviewer, admin):
    """(b) result text changed after approval fails the test; (j) revised-draft guard."""
    name = "e2e-1"
    if name not in run.state["drafts"]:
        record = create_and_approve(run, name, requester, reviewer, "bj")
        if record is None:
            return
        result = wait_run(requester, record["run_id"])
        record["first_run"] = {"run_id": record["run_id"], "status": result["status"],
                               "target_url": result.get("target_url")}
        run.state["drafts"][name] = record
        run.state["runs"].setdefault(name, []).append(
            {"run_id": record["run_id"], "status": result["status"], "kind": "first"})
        run.save()
        run.emit("bj_healthy_run", run_id=record["run_id"], status=result["status"])
    record = run.state["drafts"][name]
    try:
        rts.reset_target(E2E_CONTAINER)
        set_mode(broken=1)
        result = api_rerun(run, requester, record["run_id"])
        run.state["runs"][name].append({"run_id": result["run_id"], "status": result["status"],
                                        "kind": "broken", "via": "POST /api/v1/runs"})
        run.emit("b", case="b", run_id=result["run_id"], status=result["status"],
                 summary=result["summary"], ok=result["status"] == "failed")
    finally:
        set_mode()
    # (j): a values test whose stored run failed; the approval itself runs against the broken page.
    second = "e2e-2"
    try:
        record2 = create_and_approve(run, second, requester, reviewer, "j", broken=True)
        if record2 is None:
            return
        result = wait_run(requester, record2["run_id"])
        record2["first_run"] = {"run_id": record2["run_id"], "status": result["status"],
                                "target_url": result.get("target_url")}
        run.state["drafts"][second] = record2
        run.state["runs"].setdefault(second, []).append(
            {"run_id": record2["run_id"], "status": result["status"], "kind": "broken-first"})
        run.emit("j_broken_run", run_id=record2["run_id"], status=result["status"])
        revised = requester.post(f"/api/v1/runs/{record2['run_id']}/revised-draft",
                                 headers={"Idempotency-Key": uuid4().hex})
        check(run, "j", "revised-draft of a values case", revised, 409)
        run.emit("j_detail", detail=revised.json().get("detail"),
                 ok=revised.json().get("detail") == "credentials_in_source")
        before = psql("select count(*) from generation_requests;")[0]
        run.emit("j_requests", generation_requests=int(before))
    finally:
        set_mode()
        rts.reset_target(E2E_CONTAINER)
        run.save()


def case_c(run, requester, reviewer, admin):
    # A fresh session: e2e-0 lost its evidence in case h, e2e-1/2 already have drafts.
    session = run.state["sessions"]["e2e-c"]
    response = post_draft(requester, session["id"], VALUES["e2e-c"])
    check(run, "c", "inconsistent group", response, 409, "assessment_inconsistent")
    report = (response.json().get("detail") or {}).get("consistency") or {}
    run.emit("c_report", assessed=report.get("assessed_sessions"),
             counts=report.get("status_counts"), agreement=report.get("agreement_rate"),
             threshold=report.get("threshold"))


def case_def(run, requester, reviewer, admin):
    """(d) same person, (e) contributor, (f) missing acknowledgement, then the marker approval."""
    name = "marker-todo"
    session = run.state["sessions"][name]
    response, inputs = inputs_of(requester, session["id"])
    values = values_for(name, inputs.get("type_steps", []))
    if values is None:
        run.emit("values_mismatch", name=name)
        return
    key = f"e2e-{run.state['batch']}-{name}-{session['id'][:8]}"
    created = post_draft(requester, session["id"], values, key)
    if not check(run, "def", "request marker draft", created, 201):
        return
    draft_id = created.json()["draft_id"]
    with run.client(SAME_PERSON) as same:
        check(run, "d", "same person requests and approves", approve(same, draft_id), 409,
              "reviewer_must_differ_from_requester")
    check(run, "e", "contributor approves", approve(requester, draft_id), 404)
    check(run, "f", "reviewer without acknowledgement", approve(reviewer, draft_id, ack=False),
          409, "disposable_credentials_ack_required")
    draft = requester.get(f"/api/v1/test-generations/drafts/{draft_id}").json()
    run.emit("def_still_pending", state=draft["state"], ok=draft["state"] == "pending_review"
             and draft["linked_run_id"] is None)
    rts.reset_target(HEALTHY_CONTAINER)
    decision = approve(reviewer, draft_id)
    check(run, "def", "approve with ack", decision, 200)
    if decision.status_code == 200:
        record = {"draft_id": draft_id, "request_id": created.json()["request_id"],
                  "source_hash": created.json()["source_hash"],
                  "test_case_id": decision.json()["linked_test_case_id"],
                  "run_id": decision.json()["linked_run_id"], "project": session["project"]}
        result = wait_run(requester, record["run_id"])
        record["first_run"] = {"run_id": record["run_id"], "status": result["status"],
                               "target_url": result.get("target_url")}
        run.state["drafts"][name] = record
        run.state["runs"].setdefault(name, []).append(
            {"run_id": record["run_id"], "status": result["status"], "kind": "first"})
        run.save()
        run.emit("marker_run", run_id=record["run_id"], status=result["status"])


def case_h(run, requester, reviewer, admin):
    session = run.state["sessions"]["e2e-0"]
    path = f"/api/v1/vision/explorations/{session['id']}/operation-frames"
    deleted = admin.request("DELETE", path, json={"confirm": True})
    run.emit("h_delete_frames", status=deleted.status_code)
    check(run, "h", "evidence deleted", post_draft(requester, session["id"], VALUES["e2e-0"]),
          409, "evidence_expired")


def case_i(run, requester, reviewer, admin):
    session = run.state["sessions"]["pw-label"]
    response, inputs = inputs_of(requester, session["id"])
    run.emit("inputs", name="pw-label", status=response.status_code,
             lengths=[step["text_chars"] for step in inputs.get("type_steps", [])])
    check(run, "i", f"password label, assessment={session['status']}", post_draft(
        requester, session["id"], VALUES["pw-label"]), 409, "assessment_not_achieved")
    # Q4 stops a "Password"-labelled field at the agent, so the session ends `blocked` and the
    # draft is refused as `assessment_not_achieved` (user, 2026-11-28). `locator_unavailable` for a
    # `redacted` locator is proven by the database case in tests/test_agent_task_draft_e2e.py.


CASES = {"a": case_a, "g": case_g, "bj": case_bj, "c": case_c, "def": case_def, "h": case_h,
         "i": case_i}


def cmd_case(run, args):
    with run.client(REQUESTER) as requester, run.client(REVIEWER) as reviewer, \
            run.client(run.admin_headers) as admin:
        CASES[args.case](run, requester, reviewer, admin)
    run.save()
    return 0


# ----------------------------------------------------------------------------- scans


def db_places(value):
    """(table, column) of every public table whose stored text holds any spelling of `value`."""
    tables = [row for row in psql(
        "select table_name from information_schema.tables where table_schema='public' "
        "and table_type='BASE TABLE' and table_name <> 'alembic_version' order by 1;")]
    found = set()
    for variant in needle_variants(value):
        if "$q$" in variant:
            raise SystemExit("value contains the SQL quote tag")
        sql = " union all ".join(
            f"select '{table}', j.key from {table} x, json_each_text(row_to_json(x)) j "
            f"where position($q${variant}$q$ in j.value) > 0" for table in tables) + ";"
        found.update(tuple(row.split("|", 1)) for row in psql(sql))
    return found


def log_hits(value, since):
    counts = {}
    for container in LOG_CONTAINERS:
        result = docker("logs", "--since", since, container, timeout=120)
        data = result.stdout + result.stderr
        counts[container] = sum(data.count(v.encode("utf-8")) for v in needle_variants(value))
    return counts


def download_artifacts(run, name, run_id, client):
    target = run.out / "artifacts" / f"{name}-{run_id}"
    target.mkdir(parents=True, exist_ok=True)
    listing = client.get(f"/api/v1/runs/{run_id}/artifacts").json()
    kinds = []
    for item in listing:
        content = client.get(f"/api/v1/runs/{run_id}/artifacts/{item['id']}")
        if content.status_code != 200:
            kinds.append((item["kind"], content.status_code))
            continue
        path = target / f"{item['kind']}-{item['id']}"
        path.write_bytes(content.content)
        kinds.append((item["kind"], len(content.content)))
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                archive.extractall(target / f"{path.name}.unzipped")
    return target, kinds


def cmd_scan(run, args):
    since = run.state.get("scan_since") or run.state["meta"].get("since") or "3h"
    with run.client(REQUESTER) as client:
        for name in args.name:
            record = run.state["drafts"][name]
            for value in SCAN_VALUES[name]:
                tag = f"{name}:{len(value)}ch"
                places = db_places(value)
                declared = DECLARED_AFTER_APPROVAL
                report = {
                    "found": sorted(f"{t}.{c}" for t, c in places),
                    "unexpected": [f"{t}.{c}" for t, c in unexpected_places(places, declared)
                                   if name not in VALUE_IN_TASK_TEXT
                                   or (t, c) not in FREE_TEXT_PLACES],
                    "free_text_hits": free_text_hits(places, name),
                    "declared_missing": [f"{t}.{c}" for t, c in missing_places(places, declared)],
                    "must_be_clean_hits": clean_table_hits(places, name),
                }
                run.emit("scan_db", value=tag, **report)
                run.emit("scan_logs", value=tag, counts=log_hits(value, args.since or since))
            target, kinds = download_artifacts(run, name, record["run_id"], client)
            run.emit("artifacts", name=name, files=kinds)
            for value in SCAN_VALUES[name]:
                hits = files_containing(target, needle_variants(value))
                expected, on_failure, unexpected = artifact_verdict(hits)
                run.emit("scan_artifacts", value=f"{name}:{len(value)}ch",
                         expected_members=expected, failure_only_members=on_failure,
                         unexpected_members=unexpected)
    return 0


def cmd_summary(run, args):
    sessions = run.state["sessions"]
    positives = [sessions[n] for n in ("pos-login", "pos-todo", "pos-search", "marker-todo",
                                       "e2e-0", "e2e-1") if n in sessions]
    achieved = [s for s in positives if s["status"] == "achieved"]
    with_candidates = [s for s in achieved if s["candidates"] > 0]
    drafts = run.state["drafts"]
    passed = [n for n, r in run.state["runs"].items() if r and r[0]["status"] == "passed"]
    summary = {
        "meta": run.state.get("meta"), "sessions": len(sessions),
        "model_calls": {n: s["model_calls"] for n, s in sessions.items()},
        "positives": len(positives), "achieved": len(achieved),
        "achieved_with_candidates": len(with_candidates), "drafts_created": len(drafts),
        "first_runs_passed": passed,
        "reruns": {n: stability.rerun_summary(
            [i["status"] for i in r if i["kind"] == "rerun"]) for n, r in run.state["runs"].items()
            if any(i["kind"] == "rerun" for i in r)},
    }
    (run.out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                                          encoding="utf-8", newline="\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default=rts.DEFAULT_API)
    parser.add_argument("--headers-file", type=Path, default=rts.DEFAULT_HEADERS)
    parser.add_argument("--suite", type=Path, default=rts.DEFAULT_SUITE)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--project-suffix", default="",
                        help="append to the two e2e project names: the consistency check groups "
                        "sessions per project, so a project reused across rounds carries old ones")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("setup").set_defaults(handler=cmd_setup)
    commands.add_parser("teardown").set_defaults(handler=cmd_teardown)
    commands.add_parser("summary").set_defaults(handler=cmd_summary)
    sessions = commands.add_parser("sessions")
    sessions.add_argument("--name", action="append", required=True, choices=sorted(SESSIONS))
    sessions.add_argument("--again", action="store_true", help="submit again although recorded")
    sessions.set_defaults(handler=cmd_sessions)
    positive = commands.add_parser("positive")
    positive.add_argument("--name", action="append", required=True, choices=sorted(VALUES))
    positive.set_defaults(handler=cmd_positive)
    reruns = commands.add_parser("reruns")
    reruns.add_argument("--name", action="append", required=True)
    reruns.add_argument("--count", type=int, default=5)
    reruns.set_defaults(handler=cmd_reruns)
    case = commands.add_parser("case")
    case.add_argument("case", choices=sorted(CASES))
    case.set_defaults(handler=cmd_case)
    scan = commands.add_parser("scan")
    scan.add_argument("--name", action="append", required=True)
    scan.add_argument("--since", help="docker logs --since value, e.g. 3h")
    scan.set_defaults(handler=cmd_scan)
    return parser


def apply_project_suffix(suffix):
    """Rename the two scratch projects (not the fixture project) for this process."""
    global E2E_PROJECT, PASSWORD_PROJECT
    renames = {E2E_PROJECT: E2E_PROJECT + suffix, PASSWORD_PROJECT: PASSWORD_PROJECT + suffix}
    E2E_PROJECT, PASSWORD_PROJECT = renames[E2E_PROJECT], renames[PASSWORD_PROJECT]
    for plan in SESSIONS.values():
        plan["project"] = renames.get(plan["project"], plan["project"])


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.project_suffix:
        apply_project_suffix(args.project_suffix)
    return args.handler(Run(args), args)


if __name__ == "__main__":
    raise SystemExit(main())
