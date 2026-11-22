"""Resumable benchmark client; commands never edit code, policies or verdicts."""

import argparse
import hashlib
import json
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from evidence import (
    STATES,
    binding_error,
    derive_detection,
    diagnose,
    export_contexts,
    export_diagnostic,
    export_grounding,
    export_inventory,
    export_locator,
    export_operation,
    safe_code,
    safe_id,
)
from metrics import Assessment, Detection, OutcomeReview, content_hash, score, validate_oracle

TERMINAL = {"completed", "cancelled", "unavailable"}
ROOT = Path(__file__).resolve().parents[3]
# Optional evidence a stored session may carry (ADR-040). `none` scores as if neither existed, so
# each flag combination of a session captured with all of them can be re-scored from stored data.
SOURCES = ("click_context", "inventory")


def parse_sources(value):
    """`all` (default), `none` or a comma list of SOURCES; anything else is an error."""
    if value in (None, "all"):
        return set(SOURCES)
    chosen = set() if value == "none" else set(value.split(","))
    if not chosen <= set(SOURCES):
        raise ValueError("unknown evidence source")
    return chosen


def artifact(folder, stem, label=None):
    """`<stem>.json`, or `<stem>.<label>.json` so combinations never collide with retained files."""
    if label is not None and not label.replace("-", "").replace("_", "").isalnum():
        raise ValueError("invalid label")
    return Path(folder) / (f"{stem}.json" if label is None else f"{stem}.{label}.json")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value, *, replace=False):
    path = Path(path)
    text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    if not replace:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(text)
        return
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(text)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def retain_json(path, value):
    if path.exists():
        if read_json(path) != value:
            raise ValueError("immutable artifact differs")
    else:
        write_json(path, value)


def source_hash():
    files = []
    for directory in ("apps/control-plane", "workers/playwright/src", "packages/contracts",
                      "benchmark/vision/accuracy"):
        files.extend(p for p in (ROOT / directory).rglob("*")
                     if p.suffix in {".py", ".ts", ".tsx"} and "__pycache__" not in p.parts)
    files.extend(ROOT / name for name in (
        "pyproject.toml", "uv.lock", "docker-compose.yml", "docker-compose.codex.yml",
        "workers/playwright/package.json", "workers/playwright/package-lock.json",
    ) if (ROOT / name).exists())
    return content_hash({p.relative_to(ROOT).as_posix(): hashlib.sha256(
        p.read_text(encoding="utf-8").encode()).hexdigest() for p in sorted(files)})


def grounding_document(session_id, revision, rows, locators):
    document = {"schema_version": "vision-accuracy-grounding-v1", "session_id": session_id,
                "trace_revision": revision, "locators": export_grounding(rows, locators)}
    contexts = export_contexts(rows)
    if contexts:  # absent for sessions without `click-context-v1`: their file stays unchanged
        document["contexts"] = contexts
    return document


def inventory_document(session_id, pages):
    return {"schema_version": "vision-accuracy-inventory-v1", "session_id": session_id,
            "pages": export_inventory(pages)}


def check_grounding(document, evidence):
    """Grounding must describe the same trace and locators as the retained evidence."""
    known = {row["id"]: row for row in evidence["locators"]}
    if (document.get("schema_version") != "vision-accuracy-grounding-v1"
            or document.get("session_id") != evidence["session_id"]
            or document.get("trace_revision") != evidence["trace_revision"]
            or any(key not in known or known[key]["operation_id"] != row["operation_id"]
                   or known[key]["status"] != row["status"]
                   for key, row in document["locators"].items())
            or any(key not in {row["id"] for row in evidence["operations"]}
                   for key in document.get("contexts", {}))):
        raise ValueError("grounding does not match evidence")
    return document["locators"]


class Loop:
    def __init__(self, client, directory):
        self.client = client
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def locked(self):
        lock = self.directory / ".writer.lock"
        stream = lock.open("a+b")
        try:
            stream.seek(0, 2)
            if not stream.tell():
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                stream.seek(0)
                if sys.platform == "win32":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()  # Kernel releases the lock on process death; the file is harmless.

    def manifest(self, iteration):
        if not safe_id(iteration):
            raise ValueError("invalid iteration ID")
        path = self.directory / iteration / "manifest.json"
        data = read_json(path)
        if data.get("schema_version") != "vision-accuracy-run-v1":
            raise ValueError("unknown manifest schema")
        return path, data

    def get(self, path, **kwargs):
        response = self.client.get(path, **kwargs)
        response.raise_for_status()
        return response.json()

    def start(self, original, oracle, config, *, candidate_hash, existing=False):
        if not safe_id(original):
            raise ValueError("invalid original session")
        validate_oracle(oracle)
        if set(config) != {
            "expected_provider", "expected_model", "expected_input_policy_fingerprint",
        }:
            raise ValueError("only frozen reload policy belongs in manifest")
        with self.locked():
            for manifest in self.directory.glob("*/manifest.json"):
                if read_json(manifest).get("state") not in TERMINAL:
                    raise ValueError("resume unresolved iteration before starting another")
            active = self.get("/api/v1/vision/explorations")
            if any(row["state"] in {"queued", "running"} for row in active["items"]):
                raise ValueError("active exploration must finish before starting another")
            historical = self.get(f"/api/v1/vision/explorations/{original}") if existing else None
            if historical and historical["state"] not in TERMINAL:
                raise ValueError("only terminal sessions may be imported")
            iteration = str(uuid4())
            folder = self.directory / iteration
            folder.mkdir()
            data = {"schema_version": "vision-accuracy-run-v1", "iteration_id": iteration,
                    "created_at": datetime.now(UTC).isoformat(), "original_session_id": original,
                    "session_id": original if existing else None,
                    "idempotency_key": f"accuracy-loop:{iteration}",
                    "state": historical["state"] if historical else "not_submitted",
                    "source_hash": "historical_unverified" if existing else candidate_hash,
                    "qualification_eligible": not existing,
                    "config_hash": content_hash(config), "config": config,
                    "oracle_hash": content_hash(oracle)}
            write_json(folder / "oracle.json", oracle)
            write_json(folder / "manifest.json", data)
        return iteration

    def resume(self, iteration):
        with self.locked():
            path, data = self.manifest(iteration)
            if not data["session_id"]:
                # Persisted key survives timeout after server commit. Never allocate a new key here.
                response = self.client.post(
                    f"/api/v1/vision/explorations/{data['original_session_id']}/reload",
                    headers={"Idempotency-Key": data["idempotency_key"]}, json=data["config"],
                )
                response.raise_for_status()
                session = response.json()
                if not safe_id(session.get("id")):
                    raise ValueError("invalid session response")
                data["session_id"] = session["id"]
            session = self.get(f"/api/v1/vision/explorations/{data['session_id']}")
            if session["state"] not in STATES:
                raise ValueError("unknown exploration state")
            data["state"] = session["state"]
            data["observed_policy"] = {
                key: session[key] for key in ("max_steps", "max_hops", "max_states",
                                             "max_session_seconds", "step_timeout_seconds")
                if type(session.get(key)) is int
            }
            data["reason"] = safe_code(session.get("safe_failure_reason"))
            write_json(path, data, replace=True)
            return data

    def collect(self, iteration, *, diagnostics=()):
        with self.locked():
            path, data = self.manifest(iteration)
            if not data["session_id"]:
                raise ValueError("resume submission first")
            session_id = data["session_id"]
            base = f"/api/v1/vision/explorations/{session_id}"
            result = self.get(base + "/result")
            if result.get("schema_version") != "v1" or result.get("session_id") != session_id:
                raise ValueError("result schema/scope mismatch")
            state = result["exploration_state"]
            if state not in TERMINAL:
                raise ValueError("exploration is not terminal; resume monitoring")
            destination = path.parent / "evidence.json"
            if destination.exists():
                return read_json(destination)
            rows, raw_locators, revision = self.trace(base, session_id)
            items = [export_operation(row) for row in rows]
            locators = {}
            for locator in raw_locators:
                exported = export_locator(locator)
                locators[exported["id"]] = exported
            if len({row["id"] for row in items}) != len(items):
                raise ValueError("duplicate trace operation")
            safe_diagnostics = [record for row in diagnostics
                                if (record := export_diagnostic(row, session_id))]
            conclusion = result.get("exploration_report", {}).get("conclusion", {})
            # No target labels, handoffs, source/intent text or arbitrary nested payloads.
            allowed_conclusion = {
                "status", "coverage", "interaction_scope", "observed_controls",
                "completed_controls", "remaining_controls", "inventory_limited",
                "operations_completed", "operations_failed", "operations_rejected",
                "operations_unknown", "operations_pending", "candidates_not_attempted",
                "business_outcome",
            }
            conclusion = {key: value for key, value in conclusion.items()
                          if key in allowed_conclusion and (type(value) in {int, bool}
                          or value in ("partial", "completed", "not_established",
                                       "observed_controls_completed", "visual_buttons",
                                       "buttons", "all", "unverified"))}
            evidence = {"schema_version": "vision-accuracy-evidence-v1",
                        "session_id": session_id, "state": state, "trace_revision": revision,
                        "operations": items, "locators": list(locators.values()),
                        "diagnostics": safe_diagnostics, "runtime_conclusion": conclusion,
                        "diagnosis": diagnose(result.get("completion_reason"), items,
                                              safe_diagnostics)}
            retain_json(path.parent / "grounding.json", grounding_document(
                session_id, revision, rows, raw_locators))
            if result.get("pages"):  # only sessions with a persisted inventory (ADR-040 A3)
                retain_json(path.parent / "inventory.json",
                            inventory_document(session_id, result["pages"]))
            write_json(destination, evidence)
            data["state"] = state
            data["reason"] = safe_code(result.get("completion_reason"))
            write_json(path, data, replace=True)
            return evidence

    def trace(self, base, session_id):
        """Raw trace rows and locators of a terminal session (read-only GET, paginated)."""
        rows, locators, cursor, revision = [], {}, 0, None
        while True:
            params = {"after_sequence": cursor, "limit": 100}
            if revision:
                params["revision"] = revision
            trace = self.get(base + "/trace", params=params)
            if (trace.get("schema_version") != "v1" or trace.get("session_id") != session_id
                    or (revision and trace["revision"] != revision)):
                raise ValueError("trace schema/scope/revision mismatch")
            revision = trace["revision"]
            rows.extend(trace["items"])
            for locator in trace["locators"]:
                locators[locator.get("id")] = locator
            if not trace["has_more"]:
                return rows, list(locators.values()), revision
            if trace["next_sequence"] <= cursor:
                raise ValueError("trace pagination did not advance")
            cursor = trace["next_sequence"]

    def ground(self, iteration):
        """Add role-locator grounding to evidence collected before it was exported."""
        with self.locked():
            path, data = self.manifest(iteration)
            evidence = read_json(path.parent / "evidence.json")
            rows, locators, revision = self.trace(
                f"/api/v1/vision/explorations/{data['session_id']}", data["session_id"])
            document = grounding_document(data["session_id"], revision, rows, locators)
            check_grounding(document, evidence)
            retain_json(path.parent / "grounding.json", document)
            result = self.get(f"/api/v1/vision/explorations/{data['session_id']}/result")
            if result.get("pages"):
                retain_json(path.parent / "inventory.json",
                            inventory_document(data["session_id"], result["pages"]))
            return document

    def detect(self, iteration, *, sources=None, label=None):
        """Detection facts from the retained inventory, or the old empty ones without it."""
        chosen = parse_sources(sources)
        with self.locked():
            path, data = self.manifest(iteration)
            oracle = read_json(path.parent / "oracle.json")
            if content_hash(oracle) != data["oracle_hash"]:
                raise ValueError("oracle changed after start")
            stored = path.parent / "inventory.json"
            facts = {"identified_ids": [], "unexpected_paths": [], "inventory_complete": False,
                     "ambiguous_controls": 0, "pages_on_oracle_url": 0}
            if "inventory" in chosen and stored.exists():
                document = read_json(stored)
                if (document.get("schema_version") != "vision-accuracy-inventory-v1"
                        or document.get("session_id") != data["session_id"]):
                    raise ValueError("inventory does not match session")
                facts = derive_detection(oracle, document["pages"])
            detection = {"oracle_hash": data["oracle_hash"],
                         **{key: facts[key] for key in (
                             "identified_ids", "unexpected_paths", "inventory_complete")}}
            retain_json(artifact(path.parent, "detection.derived", label), detection)
            retain_json(artifact(path.parent, "detection.facts", label),
                        {key: facts[key] for key in ("ambiguous_controls", "pages_on_oracle_url")})
            return detection

    def frame(self, iteration, metadata):
        _, data = self.manifest(iteration)
        if metadata["availability"] != "retained" or not metadata["id"]:
            raise ValueError("frame unavailable")
        response = self.client.get(f"/api/v1/vision/explorations/{data['session_id']}"
                                   f"/operation-frames/{metadata['id']}")
        response.raise_for_status()
        if (hashlib.sha256(response.content).hexdigest() != metadata["checksum"]
                or len(response.content) != metadata["byte_count"]):
            raise ValueError("frame integrity mismatch")
        return response.content

    def record_review(self, iteration, review):
        with self.locked():
            path, data = self.manifest(iteration)
            if review.oracle_hash != data["oracle_hash"]:
                raise ValueError("review oracle mismatch")
            body = review.model_dump(mode="json")
            digest = content_hash(body)
            retain_json(path.parent / f"review-{digest}.json", body)
            return digest

    def evaluate(self, iteration, assessments, detection, *, sources=None, label=None):
        chosen = parse_sources(sources)
        with self.locked():
            path, data = self.manifest(iteration)
            evidence = read_json(path.parent / "evidence.json")
            oracle = read_json(path.parent / "oracle.json")
            if content_hash(oracle) != data["oracle_hash"]:
                raise ValueError("oracle changed after start")
            operations = {row["id"]: row for row in evidence["operations"]}
            if set(operations) != {row.operation_id for row in assessments}:
                raise ValueError("every operation requires an assessment; no omitted failures")
            locators = {row["id"]: row for row in evidence["locators"]}
            grounded = path.parent / "grounding.json"
            grounding = check_grounding(read_json(grounded), evidence) if grounded.exists() else {}
            contexts = (read_json(grounded).get("contexts", {})
                        if grounded.exists() and "click_context" in chosen else {})
            setup = [row for row in evidence["operations"] if row["purpose"] == "setup"
                     and row["action_kind"] == "navigate" and row["status"] == "completed"]
            root_page = (min(setup, key=lambda row: row["sequence"])["after_page_id"]
                         if setup else None)
            role_targets = {}
            for row in assessments:
                operation = operations[row.operation_id]
                if any(getattr(row, key) != operation[key]
                       for key in ("status", "purpose", "action_kind")):
                    raise ValueError("assessment rewrites operation")
                if row.target_verdict == row.outcome_verdict == "correct":
                    binding = locators.get(operation["locator_id"])
                    target = next((e for e in oracle["examples"] if e["id"] == row.target_id), None)
                    reason = binding_error(
                        oracle, target, binding, grounding.get(binding["id"]) if binding else None,
                        operation, root_page, row.binding_reference, contexts.get(operation["id"]))
                    if reason:
                        raise ValueError(f"assessment binding does not match oracle ({reason})")
                    # Role-bound credit is stricter than the historical path rule: one operation
                    # per target, so a repeated or mis-bound click cannot inflate accuracy.
                    if binding["path"] is None and role_targets.setdefault(
                            target["id"], row.operation_id) != row.operation_id:
                        raise ValueError("oracle target already credited by another operation")
                    for role in ("before", "after"):
                        if getattr(row, role + "_checksum") != operation[role]["checksum"]:
                            raise ValueError("assessment frame mismatch")
                        self.frame(iteration, operation[role])
                    digest = row.outcome_reference
                    if not digest or len(digest) != 64 or any(c not in "0123456789abcdef"
                                                            for c in digest):
                        raise ValueError("content-addressed outcome review required")
                    review = OutcomeReview.model_validate(read_json(
                        path.parent / f"review-{digest}.json",
                    ))
                    if (content_hash(review.model_dump(mode="json")) != digest
                            or review.operation_id != row.operation_id
                            or review.oracle_hash != data["oracle_hash"]
                            or review.verdict != row.outcome_verdict
                            or review.review_method != row.review_method
                            or review.outcome_kind != target["outcome"]["kind"]
                            or review.before_checksum != row.before_checksum
                            or review.after_checksum != row.after_checksum):
                        raise ValueError("outcome review does not match operation/oracle")
            result = score(oracle, assessments, detection)
            retain_json(artifact(path.parent, "assessments", label),
                        [row.model_dump(mode="json") for row in assessments])
            retain_json(artifact(path.parent, "detection", label),
                        detection.model_dump(mode="json"))
            retain_json(artifact(path.parent, "score", label), result)
            return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["start", "import", "resume", "collect", "ground",
                                            "detect", "evaluate"])
    parser.add_argument("--directory", type=Path, default=Path(__file__).parent / "runs")
    parser.add_argument("--api", default="http://127.0.0.1:7000")
    parser.add_argument("--headers-file", type=Path, required=True,
                        help="Private local auth headers JSON; never copied to artifacts")
    parser.add_argument("--iteration")
    parser.add_argument("--original")
    parser.add_argument("--oracle", type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--diagnostics", type=Path)
    parser.add_argument("--assessments", type=Path)
    parser.add_argument("--detection", type=Path)
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--sources", help="evaluate/detect: all (default), none, or a comma list "
                        "of click_context, inventory; scores a stored session as if only those "
                        "optional evidence sources existed")
    parser.add_argument("--label", help="evaluate/detect: write <name>.<label>.json artifacts, so "
                        "several source combinations of one iteration can be kept")
    args = parser.parse_args()
    headers = read_json(args.headers_file)
    with httpx.Client(base_url=args.api, headers=headers, timeout=30) as client:
        loop = Loop(client, args.directory)
        try:
            if args.command in {"start", "import"}:
                iteration = loop.start(args.original, read_json(args.oracle),
                                       read_json(args.policy), candidate_hash=source_hash(),
                                       existing=args.command == "import")
                print(json.dumps({"iteration_id": iteration,
                                  "state": loop.manifest(iteration)[1]["state"]}))
            elif args.command == "resume":
                result = loop.resume(args.iteration)
                print(json.dumps({key: result[key] for key in
                                  ("iteration_id", "session_id", "state", "reason")}))
            elif args.command == "collect":
                result = loop.collect(args.iteration, diagnostics=read_json(args.diagnostics)
                                      if args.diagnostics else ())
                print(json.dumps({"session_id": result["session_id"], "state": result["state"],
                                  "diagnosis": result["diagnosis"]}))
            elif args.command == "ground":
                result = loop.ground(args.iteration)
                print(json.dumps({"session_id": result["session_id"],
                                  "role_locators": len(result["locators"]),
                                  "click_contexts": len(result.get("contexts", {}))}))
            elif args.command == "detect":
                result = loop.detect(args.iteration, sources=args.sources, label=args.label)
                print(json.dumps({"identified": len(result["identified_ids"]),
                                  "unexpected": len(result["unexpected_paths"]),
                                  "inventory_complete": result["inventory_complete"]}))
            else:
                for review in read_json(args.reviews) if args.reviews else []:
                    loop.record_review(args.iteration, OutcomeReview.model_validate(review))
                result = loop.evaluate(args.iteration, [
                    Assessment.model_validate(row) for row in read_json(args.assessments)
                ], Detection.model_validate(read_json(args.detection)),
                    sources=args.sources, label=args.label)
                print(json.dumps({key: result[key] for key in ("coverage", "accuracy", "passed")}))
        except httpx.HTTPError as error:
            status = (error.response.status_code
                      if isinstance(error, httpx.HTTPStatusError) else None)
            print(json.dumps({"error": "http_failure", "status": status,
                              "resume_same_iteration": True}))
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
