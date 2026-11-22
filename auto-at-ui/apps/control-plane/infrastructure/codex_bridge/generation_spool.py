"""Scoped text jobs beneath a separate private directory; no images or credentials."""

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from auto_at.contracts.codex_bridge import canonical_bytes, content_hash
from auto_at.contracts.codex_generation import (
    CodexGenerationJob,
    CodexGenerationResponse,
    GenerationReceipt,
)

from infrastructure.codex_bridge.spool import FileSpool, SpoolError, _plain


class GenerationSpool(FileSpool):
    def load(self, job_id):
        request = CodexGenerationJob.model_validate_json(
            self.read_file(self.path(job_id), "request.json", 16_384),
        )
        self._scope(request)
        if request.job_id != job_id:
            raise SpoolError("generation identity mismatch")
        return request

    def publish(self, request, payload):
        self._scope(request)
        if not request.created_at <= datetime.now(UTC) < request.deadline:
            raise SpoolError("generation deadline expired")
        if len(payload) != request.input_bytes or hashlib.sha256(payload).hexdigest() != (
            request.input_hash
        ):
            raise SpoolError("generation input mismatch")
        with self.lock():
            if len(self.jobs()) >= self.max_pending:
                raise SpoolError("generation queue full")
            target = self.path(request.job_id)
            if target.exists():
                raise SpoolError("generation request already published")
            staging = self.root / f".staging-{uuid4()}"
            staging.mkdir(mode=0o700)
            try:
                self._write(staging, "request.json", canonical_bytes(request), exclusive=True)
                self._write(staging, "generation.json", payload, exclusive=True)
                if self.owner_uid is not None:
                    import os
                    os.chown(staging, self.owner_uid, -1)
                staging.rename(target)
            finally:
                if staging.exists():
                    self._remove(staging)

    def payload(self, request):
        self._scope(request)
        data = self.read_file(self.path(request.job_id), "generation.json", request.input_bytes)
        if (len(data) != request.input_bytes
                or hashlib.sha256(data).hexdigest() != request.input_hash):
            raise SpoolError("generation input mismatch")
        return data

    def receipt(self, request, name, expires_at):
        self._scope(request)
        receipt = GenerationReceipt(request_hash=content_hash(request), expires_at=expires_at)
        self._write(self.path(request.job_id), name, canonical_bytes(receipt),
                    exclusive=name == "claim.json")

    def checked_receipt(self, request, name):
        receipt = GenerationReceipt.model_validate_json(
            self.read_file(self.path(request.job_id), name, 4096),
        )
        if receipt.request_hash != content_hash(request) or receipt.expires_at.tzinfo is None:
            raise SpoolError("generation receipt mismatch")
        return receipt

    def authorize(self, request, expires_at):
        now = datetime.now(UTC)
        if not now < expires_at <= min(request.deadline, now + timedelta(seconds=8)):
            raise SpoolError("generation authorization invalid")
        self.receipt(request, "authorization.json", expires_at)

    def stop_reason(self, request, now):
        self._scope(request)
        if now >= request.deadline:
            return "bridge_deadline_exceeded"
        if now < request.created_at:
            return "bridge_policy_revoked"
        if self.has_file(request, "cancel.json"):
            self.checked_receipt(request, "cancel.json")
            return "bridge_cancelled"
        try:
            receipt = self.checked_receipt(request, "authorization.json")
        except FileNotFoundError:
            return "bridge_policy_revoked"
        if not now < receipt.expires_at <= min(request.deadline, now + timedelta(seconds=8)):
            return "bridge_policy_revoked"
        return None

    def claim(self, request):
        if self.stop_reason(request, datetime.now(UTC)):
            raise SpoolError("generation authorization unavailable")
        self.receipt(request, "claim.json", request.deadline)

    def cancel(self, request):
        self.receipt(request, "cancel.json", request.deadline)

    def complete(self, request, response):
        self._scope(request)
        if response.request_hash != content_hash(request):
            raise SpoolError("generation response mismatch")
        self._write(self.path(request.job_id), "response.json", canonical_bytes(response))

    def result(self, request):
        self._scope(request)
        try:
            response = CodexGenerationResponse.model_validate_json(
                self.read_file(self.path(request.job_id), "response.json", 100_000),
            )
        except FileNotFoundError:
            return None
        if response.request_hash != content_hash(request):
            raise SpoolError("generation response mismatch")
        return response

    def acknowledge(self, request):
        if self.result(request) is None:
            raise SpoolError("generation unfinished")
        self.receipt(request, "ack.json", request.deadline)

    def reconcile(self, now):
        with self.lock():
            for job_id in self.jobs():
                request = self.load(job_id)
                if now >= request.deadline:
                    self._remove(self.path(job_id))
                elif self.has_file(request, "ack.json"):
                    self.checked_receipt(request, "ack.json")
                    if self.result(request) is None:
                        raise SpoolError("generation acknowledgement invalid")
                    self._remove(self.path(job_id))
                elif self.has_file(request, "cancel.json") and self.has_file(
                    request, "response.json",
                ):
                    self.checked_receipt(request, "cancel.json")
                    self._remove(self.path(job_id))
            for staging in self.root.glob(".staging-*"):
                self._remove(staging)

    def purge_inputs(self, request):
        for name in ("generation.json", "raw-output.json"):
            path = self.path(request.job_id) / name
            if path.exists():
                _plain(path)
                path.unlink()
