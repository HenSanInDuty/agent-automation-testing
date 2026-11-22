"""Sprint runner for one engine-v4 accuracy round (phase 06). Local operator tool.

    uv run python benchmark/vision/accuracy/round_v4.py preflight
    uv run python benchmark/vision/accuracy/round_v4.py start --hypothesis "<why this run>"
    uv run python benchmark/vision/accuracy/round_v4.py wait <iteration>
    uv run python benchmark/vision/accuracy/round_v4.py collect <iteration>
    uv run python benchmark/vision/accuracy/round_v4.py auto <iteration>
    uv run python benchmark/vision/accuracy/round_v4.py score <iteration> [--findings extra.json]

`preflight` is the mandatory smoke gate: a failure means no submission and no live-run budget
spent. `start` refuses without a passing preflight of the same source hash from the last 20 min.
`auto` writes machine findings only where the after-state URL hash equals the declared destination
(or its independently reviewed redirect); everything else is listed for image review.
Private headers/policy files stay in `.pytest-artifacts/`; nothing secret is written to runs/.
"""

import argparse
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from evidence import export_download_destination  # noqa: E402
from metrics import oracle_paths  # noqa: E402
from rescore import rescore  # noqa: E402
from run import Loop, read_json, retain_json, source_hash  # noqa: E402

API = "http://127.0.0.1:7000"
HEADERS = ROOT / ".pytest-artifacts/accuracy-local-headers.json"
POLICY = ROOT / ".pytest-artifacts/accuracy-local-policy-claude.json"
ORACLE = HERE / "oracle-mongchiton-1280-v2.json"
ORIGINAL = "d69fc7fa-d35a-42b4-a546-c5919baf9044"
RUNS = HERE / "runs"
PREFLIGHT = HERE / "preflight"
TOKEN_DIR = Path.home() / ".auto-at/claude-bridge-secrets"
TERMINAL = {"completed", "unavailable", "cancelled"}
AGENT_FLAGS = ("VISION_AGENT_LOOP_ENABLED", "VISION_AGENT_CLICK_CONTEXT_ENABLED",
               "VISION_AGENT_DOM_PATH_ENABLED", "VISION_AGENT_INVENTORY_ENABLED")
# Runtime sources baked into each image (host path prefix -> container root).
SERVICES = {
    "control-plane": [("apps/control-plane", "/app/apps/control-plane"),
                      ("packages/contracts/src", "/app/packages/contracts/src")],
    "temporal-worker": [("apps/control-plane", "/app/apps/control-plane"),
                        ("packages/contracts/src", "/app/packages/contracts/src")],
    "playwright-worker": [("workers/playwright/src", "/worker/src")],
}
MOUNT_SAFE_EXCLUDE = (".spec.ts", "/fixtures/", "__pycache__", "/tests/")


def sql(query):
    out = subprocess.run(["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "auto_at",
                          "-d", "auto_at", "-Atc", query], cwd=ROOT, capture_output=True,
                         text=True, check=True)
    return json.loads(out.stdout)


def client():
    return httpx.Client(base_url=API, headers=read_json(HEADERS), timeout=30)


def lf_sha(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def tracked(prefix):
    names = subprocess.run(["git", "ls-files", prefix], cwd=ROOT, capture_output=True,
                           text=True, check=True).stdout.split()
    return [name for name in names if name.endswith((".py", ".ts"))
            and not any(part in "/" + name for part in MOUNT_SAFE_EXCLUDE)]


def check_images(report):
    mismatches = []
    for service, roots in SERVICES.items():
        container = f"auto-at-ui-{service}-1"
        for host_root, remote_root in roots:
            # Images built from a Windows working copy may carry CRLF: compare LF-normalized.
            archive = subprocess.run(["docker", "exec", container, "tar", "-C", remote_root,
                                      "-cf", "-", "."], capture_output=True, check=True).stdout
            remote = {}
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                for member in tar.getmembers():
                    if member.isfile() and member.name.endswith((".py", ".ts")):
                        body = tar.extractfile(member).read().replace(b"\r\n", b"\n")
                        remote[member.name.removeprefix("./")] = hashlib.sha256(body).hexdigest()
            for name in tracked(host_root):
                relative = name[len(host_root) + 1:]
                if remote.get(relative) != lf_sha(ROOT / name):
                    mismatches.append(f"{service}:{name}")
        report[f"image:{service}"] = subprocess.run(
            ["docker", "inspect", "--format", "{{.Image}}", container],
            capture_output=True, text=True, check=True).stdout.strip()
    return mismatches


def worker_flags():
    env = subprocess.run(["docker", "inspect", "--format",
                          "{{range .Config.Env}}{{println .}}{{end}}",
                          "auto-at-ui-temporal-worker-1"], capture_output=True, text=True,
                         check=True).stdout.splitlines()
    values = dict(line.split("=", 1) for line in env if "=" in line)
    return {flag: values.get(flag, "unset") for flag in AGENT_FLAGS}


def token_hours():
    oauth = json.loads((Path.home() / ".claude/.credentials.json").read_text("utf-8"))
    return (oauth["claudeAiOauth"]["expiresAt"] / 1000 - time.time()) / 3600


def worker_open_close():
    """Open and close one worker session inside the container: browser launch, no LLM, no click."""
    # Same shape as the v4 controller open (vision_trace_events.py) for a frozen-input reload.
    payload = {"contract_version": "v4", "required_capabilities": [
                   "dom-observation-v1", "viewport-context-v1", "target-preflight-v1",
                   "step-timeout-v1"],
               "tenant_id": "default", "project_id": "00000000-0000-4000-8000-000000000001",
               "target_url": "https://mongchiton.vn", "allowed_origins": ["https://mongchiton.vn"],
               "max_session_seconds": 120, "step_timeout_seconds": 120, "max_states": 100,
               "max_hops": 20, "max_screenshot_bytes": 1000000, "interaction_scope": "all",
               "fencing_token": 1}
    script = r"""
const crypto = require("node:crypto");
const base = JSON.parse(require("node:fs").readFileSync(0, "utf8"));
(async () => {
  const p = { ...base, session_id: crypto.randomUUID(),
              deadline: new Date(Date.now() + 120000).toISOString() };
  const h = { "content-type": "application/json",
    "x-auto-at-vision-worker-secret": process.env.VISION_WORKER_SECRET || "",
    "x-auto-at-vision-tenant-id": p.tenant_id, "x-auto-at-vision-project-id": p.project_id,
    "x-auto-at-vision-fencing-token": "1" };
  const t = Date.now();
  const r = await fetch("http://127.0.0.1:7100/visual-explorations",
                        { method: "POST", headers: h, body: JSON.stringify(p) });
  const opened = r.status;
  const d = await fetch(`http://127.0.0.1:7100/visual-explorations/${p.session_id}`,
                        { method: "DELETE", headers: h });
  console.log(JSON.stringify({ open: opened, open_ms: Date.now() - t, close: d.status }));
})().catch(e => console.log(JSON.stringify({ error: e.name })));
"""
    out = subprocess.run(["docker", "exec", "-i", "auto-at-ui-playwright-worker-1", "node", "-e",
                          script], input=json.dumps(payload), capture_output=True, text=True,
                         timeout=180)
    try:
        return json.loads(out.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"error": "no_output"}


def preflight():
    report = {"at": datetime.now(UTC).isoformat(), "source_hash": source_hash(), "checks": {}}
    checks = report["checks"]
    with client() as api:
        active = [row["id"] for row in api.get("/api/v1/vision/explorations").json()["items"]
                  if row["state"] in {"queued", "running"}]
        checks["no_active_session"] = not active
        unresolved = [p.parent.name for p in RUNS.glob("*/manifest.json")
                      if read_json(p).get("state") not in TERMINAL]
        checks["no_unresolved_iteration"] = not unresolved
        providers = api.get("/api/v1/vision/providers").json()["items"]
        readiness = next((p["bridge_readiness"] for p in providers if p["id"] == "claude_cli"),
                         None) or {}
        ready_keys = ("configured", "online", "authenticated", "capabilities_qualified")
        checks["claude_bridge_ready"] = (all(readiness.get(k) is True for k in ready_keys)
                                         and not readiness.get("busy"))
    flags = worker_flags()
    report["agent_flags"] = flags
    checks["agent_loop_flags_off"] = all(v in {"unset", "false"} for v in flags.values())
    mismatches = check_images(report)
    report["image_mismatches"] = mismatches[:50]
    checks["images_match_tree"] = not mismatches
    probe = subprocess.run(["docker", "exec", "auto-at-ui-temporal-worker-1", "uv", "run",
                            "--no-sync", "python", "-c",
                            "import httpx; r=httpx.get('http://playwright-worker:7100/"
                            "visual-explorations',timeout=10); "
                            "raise SystemExit(0 if r.status_code == 401 else 1)"],
                           capture_output=True)
    checks["worker_http_auth_required"] = probe.returncode == 0
    hours = token_hours()
    report["claude_token_hours"] = round(hours, 2)
    if hours >= 3:
        exported = subprocess.run(["uv", "run", "python", "scripts/export_claude_bridge_token.py",
                                   str(TOKEN_DIR)], cwd=ROOT, capture_output=True, text=True)
        checks["claude_token_exported"] = exported.returncode == 0
    checks["claude_token_3h"] = hours >= 3
    smoke = worker_open_close()
    report["worker_open_close"] = smoke
    checks["worker_open_close"] = smoke.get("open") == 200 and smoke.get("close") == 200
    report["passed"] = all(checks.values())
    PREFLIGHT.mkdir(exist_ok=True)
    name = report["at"][:19].replace(":", "") + ".json"
    retain_json(PREFLIGHT / name, report)
    print(json.dumps({"passed": report["passed"], "checks": checks,
                      "image_mismatches": report["image_mismatches"][:10],
                      "token_hours": report["claude_token_hours"]}, indent=2))
    return 0 if report["passed"] else 1


def last_preflight():
    reports = sorted(PREFLIGHT.glob("*.json")) if PREFLIGHT.is_dir() else []
    return read_json(reports[-1]) if reports else None


def start(hypothesis):
    report = last_preflight()
    current = source_hash()
    if not report or not report["passed"] or report["source_hash"] != current:
        raise SystemExit("no passing preflight for the current source; run preflight first")
    age = (datetime.now(UTC) - datetime.fromisoformat(report["at"])).total_seconds()
    if age > 1200:
        raise SystemExit("preflight older than 20 minutes; run it again")
    with client() as api:
        loop = Loop(api, RUNS)
        iteration = loop.start(ORIGINAL, read_json(ORACLE), read_json(POLICY),
                               candidate_hash=current)
        print(json.dumps({"iteration_id": iteration}), flush=True)
        data = loop.resume(iteration)
        retain_json(RUNS / iteration / "provenance.json", {
            "session_id": data["session_id"], "source_hash": current, "engine": "v4",
            "oracle": ORACLE.name, "preflight_at": report["at"], "hypothesis": hypothesis,
            "images": {k: v for k, v in report.items() if k.startswith("image:")},
            "agent_flags": report["agent_flags"], "observed_policy": data["observed_policy"]})
    print(json.dumps({k: data[k] for k in ("iteration_id", "session_id", "state")}))


def wait(iteration, deadline_minutes=40):
    with client() as api:
        loop = Loop(api, RUNS)
        end = time.time() + deadline_minutes * 60
        while time.time() < end:
            data = loop.resume(iteration)
            if data["state"] in TERMINAL:
                print(json.dumps({k: data[k] for k in ("iteration_id", "session_id", "state",
                                                       "reason")}))
                return 0
            time.sleep(20)
    print(json.dumps({"iteration_id": iteration, "state": "still_running"}))
    return 1


def collect(iteration):
    folder = RUNS / iteration
    with client() as api:
        loop = Loop(api, RUNS)
        data = loop.resume(iteration)
        if data["state"] not in TERMINAL:
            raise SystemExit("not terminal")
        evidence = loop.collect(iteration)
        session = data["session_id"]
        result = api.get(f"/api/v1/vision/explorations/{session}/result").json()
        retain_json(folder / "inventory-evidence.json", [
            {**{k: page[k] for k in ("state_id", "url_fingerprint", "truncated", "skipped_count",
                                     "scrollable")},
             "keys": [control["key"] for control in page["controls"]]}
            for page in result.get("pages") or ()])
        verified = 0
        for operation in evidence["operations"]:
            for role in ("before", "after"):
                if operation[role]["availability"] == "retained":
                    loop.frame(iteration, operation[role])
                    verified += 1
    logs = subprocess.run(["docker", "logs", "auto-at-ui-playwright-worker-1"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    downloads = []
    for line in (logs.stdout + logs.stderr).splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and (record := export_download_destination(row, session)):
            downloads.append(record)
    retain_json(folder / "download-evidence.json", downloads)
    states = sql(
        "SELECT COALESCE(json_agg(json_build_object('state_id',id,'after_checksum',"
        "screenshot_checksum,'operation_id',(checkpoint->'ancestor_operation_ids')->>-1,"
        "'url_fingerprint',checkpoint->>'url_fingerprint','page_url',checkpoint->>'page_url',"
        "'scroll_x',checkpoint->'scroll_x',"
        "'scroll_y',checkpoint->'scroll_y','hop',hop) ORDER BY created_at),'[]'::json) "
        f"FROM visual_exploration_states WHERE tenant_id='demo-tenant' AND session_id='{session}';")
    retain_json(folder / "state-evidence.json", states)
    jobs = sql(
        "SELECT COALESCE(json_agg(json_build_object('request_sequence',request_sequence,"
        "'status',status,'stage',stage,'input_tokens',usage->'input_tokens','output_tokens',"
        "usage->'output_tokens','safe_reason',safe_reason)),'[]'::json) FROM codex_bridge_jobs "
        f"WHERE tenant_id='demo-tenant' AND session_id='{session}';")
    retain_json(folder / "usage.json", {"jobs": jobs, "model_jobs": len(jobs),
                                        "monetary_cost_usd": None, "cost_status": "not_reported"})
    ops = evidence["operations"]
    summary = {"operations": len(ops), "frames_verified": verified,
               "frames_unavailable": 2 * len(ops) - verified, "model_jobs": len(jobs),
               "downloads": len(downloads), "diagnosis": evidence["diagnosis"],
               "state": data["state"], "reason": data["reason"]}
    retain_json(folder / "collect-summary.json", summary)
    print(json.dumps(summary, indent=2))


def plain(url):
    """Query/fragment-free URL with one trailing-slash form, as checkpoint page_url stores it."""
    return url.split("#", 1)[0].split("?", 1)[0].rstrip("/") if isinstance(url, str) else None


def destinations(target):
    """Accepted after-page URLs: the declared destination plus its independently reviewed
    redirect chain (redirect-review-*.json), compared without query values."""
    declared = plain(target["outcome"].get("url"))
    if not declared:
        return set()
    accepted = {declared}
    for review in sorted(HERE.glob("redirect-review-*.json")):
        for row in read_json(review).get("rows", ()):
            chain = [plain(step.get("url")) for step in row.get("chain") or ()]
            if chain and chain[0] == declared:
                accepted |= {url for url in chain if url}
    return accepted


MCT47_PLAYER = hashlib.sha256(b"https://mongchiton.vn/#true").hexdigest()


def machine_finding(target, operation, state, downloads):
    """A finding when a machine rule proves the declared outcome, else None (image review)."""
    kind = target["outcome"]["kind"]
    if target["id"] == "mct-47" and state.get("url_fingerprint") == MCT47_PLAYER:
        return ("Machine rule: after-state URL is https://mongchiton.vn/#true, the embedded "
                "player state of the declared video (video-copies-probe-20261122.json). "
                "No playback claim.")
    for record in downloads:
        chain = record.get("navigation_chain") or []
        if (record.get("operation_id") == operation["id"] and record.get("status") == "completed"
                and chain and chain[0].get("url_sha256") == target["outcome"].get("url_sha256")):
            return ("Machine rule: click-bound download chain starts with the exact declared URL "
                    "hash and completes; no installation or execution claimed.")
    if kind in {"navigation_destination", "popup_destination"}:
        page = plain(state.get("page_url"))
        if page and page in destinations(target):
            return (f"Machine rule: after-state page URL {page} equals the declared destination or "
                    "its independently reviewed redirect (query values ignored). Destination only.")
    return None


def auto(iteration):
    folder = RUNS / iteration
    oracle = read_json(folder / "oracle.json")
    evidence = read_json(folder / "evidence.json")
    states = {row["operation_id"]: row for row in read_json(folder / "state-evidence.json")}
    downloads = read_json(folder / "download-evidence.json")
    locators = {row["id"]: row for row in evidence["locators"]}
    findings, review = {}, []
    credited = set()
    for operation in evidence["operations"]:
        if operation["purpose"] != "explore" or operation["action_kind"] not in {"click", "type"}:
            continue
        path = (locators.get(operation["locator_id"]) or {}).get("path")
        target = next((item for item in oracle["examples"] if path in oracle_paths(item)), None)
        row = {"sequence": operation["sequence"], "status": operation["status"],
               "target": target["id"] if target else None,
               "kind": target["outcome"]["kind"] if target and target["expected"] else None}
        if not target or not target["expected"] or operation["status"] != "completed":
            row["why"] = "unbound, negative or not completed: no credit"
            review.append(row)
            continue
        finding = machine_finding(target, operation, states.get(operation["id"]) or {}, downloads)
        if finding and target["id"] not in credited:
            findings[str(operation["sequence"])] = f"{target['id']}: {finding}"
            credited.add(target["id"])
        else:
            row["why"] = ("duplicate target" if finding else
                          "no machine rule proves the outcome: review before/after images")
            row["before"], row["after"] = operation["before"], operation["after"]
            review.append(row)
    retain_json(folder / "auto-findings.json", findings)
    retain_json(folder / "needs-review.json", review)
    print(json.dumps({"auto_findings": len(findings), "needs_review": len(review)}))


def score(iteration, extra):
    folder = RUNS / iteration
    findings = {}
    for path in [folder / "auto-findings.json", *extra]:
        for key, value in read_json(path).items():
            if key.startswith("_"):
                continue
            if key in findings:
                raise SystemExit(f"duplicate finding for sequence {key}")
            findings[key] = value
    out, result = rescore(folder, read_json(folder / "oracle.json"), findings)
    summary = {key: result[key] for key in ("coverage", "accuracy", "detection_precision",
                                            "detection_recall", "inventory_complete", "passed",
                                            "remaining_targets", "unsafe_operations",
                                            "unsettled_operations")}
    print(out)
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["preflight", "start", "wait", "collect", "auto",
                                            "score"])
    parser.add_argument("iteration", nargs="?")
    parser.add_argument("--hypothesis", default="sprint phase 06 live run")
    parser.add_argument("--findings", type=Path, action="append", default=[])
    args = parser.parse_args()
    if args.command == "preflight":
        return preflight()
    if args.command == "start":
        return start(args.hypothesis)
    if not args.iteration:
        parser.error("iteration required")
    return {"wait": wait, "collect": collect, "auto": auto}.get(
        args.command, lambda it: score(it, args.findings))(args.iteration)


if __name__ == "__main__":
    raise SystemExit(main() or 0)
