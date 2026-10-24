"""Bounded atomic files for one trusted local producer/consumer tenant.

The root must be private to the deployment. Paths do not replace filesystem ACLs.
No recursive deletion or model-supplied path is used here.
"""

import hashlib
import json
import os
import stat
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from auto_at.contracts.codex_bridge import (
    CodexBridgeEvent,
    CodexBridgeReceipt,
    CodexBridgeRequest,
    CodexBridgeResponse,
    CodexDomObservation,
    canonical_bytes,
    content_hash,
)
from domain.codex_bridge import (
    CLI_VERSION,
    validate_observation,
    validate_request_time,
    validate_response,
)

FILES = frozenset(
    {
        "request.json",
        "dom.json",
        "response.schema.json",
        "screenshot.png",
        "claim.json",
        "authorization.json",
        "cancel.json",
        "ack.json",
        "response.json",
        "events.jsonl",
        "raw-output.json",
    }
)


class SpoolError(ValueError):
    """Safe error; never includes file contents or caller-controlled diagnostics."""


def _plain(path: Path, *, directory: bool = False) -> None:
    info = path.lstat()
    if (
        stat.S_ISLNK(info.st_mode)
        or getattr(info, "st_file_attributes", 0) & 0x400
        or (not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1))
        or (directory and not stat.S_ISDIR(info.st_mode))
    ):
        raise SpoolError("unsafe bridge path")


class FileSpool:
    def __init__(self, root: Path, bridge_id: UUID, tenant_id: str, max_pending: int = 10):
        if not root.is_absolute() or ".." in root.parts:
            raise SpoolError("bridge root must be absolute")
        for parent in reversed((root, *root.parents)):
            if parent.exists():
                _plain(parent, directory=True)
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        _plain(root, directory=True)
        self.root = root.resolve(strict=True)
        self.bridge_id, self.tenant_id = bridge_id, tenant_id
        if not 1 <= max_pending <= 10:
            raise SpoolError("invalid queue bound")
        self.max_pending = max_pending

    def _root(self):
        for parent in (self.root, *self.root.parents):
            _plain(parent, directory=True)

    def _scope(self, request: CodexBridgeRequest):
        if request.bridge_id != self.bridge_id or request.tenant_id != self.tenant_id:
            raise SpoolError("bridge scope mismatch")

    def path(self, job_id: UUID) -> Path:
        self._root()
        path = self.root / str(UUID(str(job_id)))
        if path.exists() or path.is_symlink():
            _plain(path, directory=True)
            if path.resolve(strict=True).parent != self.root:
                raise SpoolError("bridge path escaped root")
        return path

    def read_file(self, directory: Path, name: str, limit: int) -> bytes:
        if name not in FILES or directory.parent != self.root:
            raise SpoolError("unknown bridge file")
        self._root()
        _plain(directory, directory=True)
        path = directory / name
        _plain(path)
        with path.open("rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise SpoolError("unsafe bridge file")
            data = source.read(limit + 1)
        if len(data) > limit:
            raise SpoolError("bridge file exceeds limit")
        return data

    def _write(self, directory: Path, name: str, data: bytes, *, exclusive=False):
        self._root()
        _plain(directory, directory=True)
        if directory != self.root and directory.parent != self.root:
            raise SpoolError("bridge path escaped root")
        target = directory / name
        if target.exists() or target.is_symlink():
            _plain(target)
        if exclusive:
            with target.open("xb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            return
        temporary = directory / f".atomic-{uuid4()}"
        try:
            with temporary.open("xb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                _plain(temporary)
                temporary.unlink()

    @contextmanager
    def lock(self, consumer=False):
        self._root()
        path = self.root / (".consumer.lock" if consumer else ".producer.lock")
        if path.exists() or path.is_symlink():
            _plain(path)
        with path.open("a+b") as handle:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                if handle.read(1) == b"":
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)

    def jobs(self) -> list[UUID]:
        self._root()
        jobs = []
        for child in self.root.iterdir():
            if child.name.startswith("."):
                continue
            try:
                job_id = UUID(child.name)
            except ValueError as exc:
                raise SpoolError("unexpected bridge root entry") from exc
            if str(job_id) != child.name:
                raise SpoolError("aliased bridge job")
            self.path(job_id)
            jobs.append(job_id)
        return sorted(jobs, key=str)

    def load(self, job_id: UUID) -> CodexBridgeRequest:
        directory = self.path(job_id)
        for item in directory.iterdir():
            if item.name not in FILES and not item.name.startswith(".atomic-"):
                raise SpoolError("unexpected bridge job file")
            _plain(item)
        request = CodexBridgeRequest.model_validate_json(
            self.read_file(directory, "request.json", 16_384),
        )
        self._scope(request)
        if request.job_id != job_id:
            raise SpoolError("bridge job identity mismatch")
        return request

    def verify_inputs(self, request: CodexBridgeRequest) -> tuple[bytes, bytes]:
        self._scope(request)
        directory = self.path(request.job_id)
        dom = self.read_file(directory, "dom.json", request.inputs.dom_bytes)
        schema = self.read_file(directory, "response.schema.json", request.inputs.schema_bytes)
        for data, expected_hash, length in (
            (dom, request.inputs.dom_sha256, request.inputs.dom_bytes),
            (schema, request.inputs.schema_sha256, request.inputs.schema_bytes),
        ):
            if len(data) != length or hashlib.sha256(data).hexdigest() != expected_hash:
                raise SpoolError("bridge input integrity mismatch")
        validate_observation(request, CodexDomObservation.model_validate_json(dom))
        if request.stage == "image":
            image = self.read_file(directory, "screenshot.png", request.inputs.screenshot_bytes)
            if (
                len(image) != request.inputs.screenshot_bytes
                or hashlib.sha256(image).hexdigest() != request.inputs.screenshot_sha256
            ):
                raise SpoolError("bridge image integrity mismatch")
        elif (directory / "screenshot.png").exists():
            raise SpoolError("unconsented image")
        return dom, schema

    def publish(self, request, dom: bytes, schema: bytes, screenshot: bytes | None = None):
        self._scope(request)
        validate_request_time(request, datetime.now(UTC))
        with self.lock():
            if len(self.jobs()) >= self.max_pending:
                raise SpoolError("bridge_queue_full")
            target = self.path(request.job_id)
            if target.exists():
                raise SpoolError("duplicate bridge job")
            staging = self.root / f".staging-{uuid4()}"
            staging.mkdir(mode=0o700)
            try:
                for name, data in (
                    ("request.json", canonical_bytes(request)),
                    ("dom.json", dom),
                    ("response.schema.json", schema),
                    ("screenshot.png", screenshot),
                ):
                    if data is not None:
                        if len(data) > (5_000_000 if name == "screenshot.png" else 65_536):
                            raise SpoolError("bridge input exceeds limit")
                        self._write(staging, name, data, exclusive=True)
                # Validate everything before publication, using the exact eventual job inputs.
                obs = CodexDomObservation.model_validate_json(dom)
                validate_observation(request, obs)
                if (
                    hashlib.sha256(schema).hexdigest() != request.inputs.schema_sha256
                    or len(schema) != request.inputs.schema_bytes
                    or (screenshot is not None) != (request.stage == "image")
                ):
                    raise SpoolError("bridge input integrity mismatch")
                if screenshot is not None and (
                    hashlib.sha256(screenshot).hexdigest() != request.inputs.screenshot_sha256
                    or len(screenshot) != request.inputs.screenshot_bytes
                ):
                    raise SpoolError("bridge image integrity mismatch")
                staging.rename(target)
            finally:
                if staging.exists():
                    self._remove(staging)

    def _receipt(self, request, status, expiry, nonce):
        return CodexBridgeReceipt(
            **{
                key: getattr(request, key)
                for key in (
                    "tenant_id",
                    "project_id",
                    "session_id",
                    "fencing_token",
                    "job_id",
                    "bridge_id",
                )
            },
            request_hash=content_hash(request),
            claim_nonce=nonce,
            status=status,
            recorded_at=datetime.now(UTC),
            authorization_expires_at=expiry,
        )

    def _matches(self, request, receipt):
        expected = self._receipt(
            request,
            receipt.status,
            receipt.authorization_expires_at,
            receipt.claim_nonce,
        )
        for field in (
            "tenant_id",
            "project_id",
            "session_id",
            "fencing_token",
            "job_id",
            "bridge_id",
            "request_hash",
        ):
            if getattr(expected, field) != getattr(receipt, field):
                raise SpoolError("bridge receipt scope mismatch")

    def authorize(self, request, expires_at):
        self._scope(request)
        now = datetime.now(UTC)
        if not now < expires_at <= request.deadline or (expires_at - now).total_seconds() > 10:
            raise SpoolError("invalid authorization expiry")
        if content_hash(self.load(request.job_id)) != content_hash(request):
            raise SpoolError("bridge request changed")
        receipt = self._receipt(request, "queued", expires_at, UUID(int=0))
        self._write(self.path(request.job_id), "authorization.json", canonical_bytes(receipt))

    def stop_reason(self, request, now: datetime) -> str | None:
        self._scope(request)
        if now >= request.deadline:
            return "bridge_deadline_exceeded"
        if now < request.created_at:
            return "bridge_policy_revoked"
        directory = self.path(request.job_id)
        if (directory / "cancel.json").exists():
            receipt = CodexBridgeReceipt.model_validate_json(
                self.read_file(directory, "cancel.json", 4096),
            )
            self._matches(request, receipt)
            if receipt.status != "cancelled":
                raise SpoolError("invalid cancellation receipt")
            return "bridge_cancelled"
        try:
            receipt = CodexBridgeReceipt.model_validate_json(
                self.read_file(directory, "authorization.json", 4096),
            )
        except FileNotFoundError:
            return "bridge_policy_revoked"
        self._matches(request, receipt)
        ttl = (receipt.authorization_expires_at - receipt.recorded_at).total_seconds()
        if (
            not receipt.recorded_at <= now < receipt.authorization_expires_at <= request.deadline
            or not 0 < ttl <= 10
            or receipt.status != "queued"
        ):
            return "bridge_policy_revoked"
        return None

    def claim(self, request):
        self._scope(request)
        if self.stop_reason(request, datetime.now(UTC)):
            raise SpoolError("bridge authorization unavailable")
        self.verify_inputs(request)
        nonce = uuid4()
        receipt = self._receipt(request, "claimed", request.deadline, nonce)
        self._write(
            self.path(request.job_id),
            "claim.json",
            canonical_bytes(receipt),
            exclusive=True,
        )
        return nonce

    def cancel(self, request):
        self._scope(request)
        receipt = self._receipt(request, "cancelled", request.deadline, UUID(int=0))
        self._write(self.path(request.job_id), "cancel.json", canonical_bytes(receipt))

    def complete(self, request, response):
        self._scope(request)
        if response.request_hash != content_hash(request):
            raise SpoolError("bridge response mismatch")
        if response.output:
            validate_response(request, response, now=datetime.now(UTC))
            if self.stop_reason(request, datetime.now(UTC)):
                raise SpoolError("bridge authorization unavailable")
        if self.has_file(request, "response.json"):
            raise SpoolError("duplicate terminal result")
        self._write(self.path(request.job_id), "response.json", canonical_bytes(response))

    def result(self, request):
        self._scope(request)
        try:
            response = CodexBridgeResponse.model_validate_json(
                self.read_file(self.path(request.job_id), "response.json", 65_536),
            )
        except FileNotFoundError:
            return None
        validate_response(request, response, now=datetime.now(UTC))
        return response

    def stages(self, request):
        """Return only scoped, ordered receipts; no raw CLI output crosses this port."""
        self._scope(request)
        if not self.has_file(request, "claim.json"):
            return ()
        receipt = CodexBridgeReceipt.model_validate_json(
            self.read_file(self.path(request.job_id), "claim.json", 4096),
        )
        self._matches(request, receipt)
        if (
            receipt.status != "claimed"
            or receipt.claim_nonce.int == 0
            or not request.created_at <= receipt.recorded_at <= datetime.now(UTC)
        ):
            raise SpoolError("invalid claim receipt")
        if not self.has_file(request, "events.jsonl"):
            return ()
        records = tuple(
            CodexBridgeEvent.model_validate_json(line)
            for line in self.read_file(
                self.path(request.job_id), "events.jsonl", 65_536
            ).splitlines()
        )
        if len(records) > 64 or any(
            record.job_id != request.job_id
            or record.sequence != index + 1
            or not receipt.recorded_at <= record.recorded_at <= datetime.now(UTC)
            for index, record in enumerate(records)
        ):
            raise SpoolError("invalid stage receipts")
        return records

    def cancellation_acknowledged(self, request):
        self._scope(request)
        self._root()
        return not self.path(request.job_id).exists()

    def _remove(self, directory):
        self._root()
        if directory.parent != self.root or directory.resolve().parent != self.root:
            raise SpoolError("unsafe cleanup target")
        _plain(directory, directory=True)
        files = list(directory.iterdir())
        for file in files:
            if file.name not in FILES and not file.name.startswith(".atomic-"):
                raise SpoolError("unexpected cleanup entry")
            _plain(file)
        for file in files:
            _plain(file)
            file.unlink()
        directory.rmdir()

    def acknowledge(self, request):
        self._scope(request)
        if self.result(request) is None:
            raise SpoolError("cannot acknowledge unfinished job")
        receipt = self._receipt(request, "completed", request.deadline, UUID(int=0))
        self._write(self.path(request.job_id), "ack.json", canonical_bytes(receipt))

    def reconcile(self, now: datetime):
        """Caller owns the consumer lock; producer lock protects unpublished staging."""
        with self.lock():
            for job_id in self.jobs():
                request = self.load(job_id)
                if request.deadline <= now:
                    self._remove(self.path(job_id))
                elif self.has_file(request, "cancel.json") and self.has_file(
                    request, "response.json"
                ):
                    # Only this locked consumer removes jobs, after its child has exited.
                    if self.stop_reason(request, now) != "bridge_cancelled":
                        raise SpoolError("invalid cancellation")
                    self._remove(self.path(job_id))
                elif self.has_file(request, "ack.json"):
                    receipt = CodexBridgeReceipt.model_validate_json(
                        self.read_file(self.path(job_id), "ack.json", 4096),
                    )
                    self._matches(request, receipt)
                    if receipt.status != "completed" or self.result(request) is None:
                        raise SpoolError("invalid acknowledgement")
                    self._remove(self.path(job_id))
            for staging in self.root.glob(".staging-*"):
                UUID(staging.name.removeprefix(".staging-"))
                self._remove(staging)

    def has_file(self, request, name):
        self._scope(request)
        if name not in FILES:
            raise SpoolError("unknown bridge file")
        path = self.path(request.job_id) / name
        if path.exists() or path.is_symlink():
            _plain(path)
            return True
        return False

    def purge_inputs(self, request):
        self._scope(request)
        for name in ("dom.json", "response.schema.json", "screenshot.png", "raw-output.json"):
            if self.has_file(request, name):
                (self.path(request.job_id) / name).unlink()

    def record_stage(self, request, stage, usage=None):
        self._scope(request)
        directory = self.path(request.job_id)
        records = []
        if self.has_file(request, "events.jsonl"):
            records = [
                CodexBridgeEvent.model_validate_json(line)
                for line in self.read_file(directory, "events.jsonl", 65_536).splitlines()
            ]
        if any(
            record.job_id != request.job_id or record.sequence != index + 1
            for index, record in enumerate(records)
        ):
            raise SpoolError("invalid progress record")
        if len(records) >= 64 or records and records[-1].stage == stage:
            return
        records.append(
            CodexBridgeEvent(
                sequence=len(records) + 1,
                job_id=request.job_id,
                recorded_at=datetime.now(UTC),
                stage=stage,
                usage=usage,
            )
        )
        data = b"".join(canonical_bytes(record) + b"\n" for record in records)
        self._write(directory, "events.jsonl", data)

    def heartbeat(self, readiness: dict):
        payload = {
            "bridge_id": str(self.bridge_id),
            "tenant_id": self.tenant_id,
            "recorded_at": datetime.now(UTC).isoformat(),
            "readiness": readiness,
            "model": "gpt-6-luna",
            "protocol": "v1",
            "cli_version": CLI_VERSION,
        }
        self._write(self.root, ".heartbeat.json", json.dumps(payload).encode())
