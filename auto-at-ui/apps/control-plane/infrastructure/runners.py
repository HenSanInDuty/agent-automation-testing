"""Replaceable local transport and verified local artifact port for Phase 2."""

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from auto_at.contracts.execution import TestExecutionRequest, TestExecutionResult
from domain.entities import ArtifactRecord
from domain.ports import ArtifactRepository

from infrastructure.artifacts.rustfs import RustFSArtifactStore
from infrastructure.observability import log_event

logger = logging.getLogger(__name__)


class RunnerUnavailableError(RuntimeError):
    pass


class HttpPlaywrightTransport:
    """The local HTTP boundary can be replaced by a durable workflow transport."""

    def __init__(
        self, worker_url: str, timeout_seconds: float = 90, progress_tenant_id: str | None = None
    ) -> None:
        self._url = f"{worker_url.rstrip('/')}/execute"
        self._timeout_seconds = timeout_seconds
        self._progress_tenant_id = progress_tenant_id

    def execute(self, request: TestExecutionRequest) -> TestExecutionResult:
        body = json.dumps(request.model_dump(mode="json")).encode()
        try:
            headers = {"Content-Type": "application/json"}
            if self._progress_tenant_id:
                headers["X-Auto-AT-Progress-Tenant-ID"] = self._progress_tenant_id
            with urlopen(
                Request(self._url, data=body, headers=headers), timeout=self._timeout_seconds
            ) as response:
                return TestExecutionResult.model_validate_json(response.read())
        except TimeoutError as error:
            log_event(
                logger,
                logging.WARNING,
                "runner.request.timeout",
                "Playwright worker timed out.",
                run_id=request.run_id,
                correlation_id=request.correlation_id,
                timeout_seconds=self._timeout_seconds,
            )
            raise RunnerUnavailableError("Playwright worker timed out") from error
        except (URLError, ValueError) as error:
            raise RunnerUnavailableError(
                "Playwright worker did not return a valid result"
            ) from error

    def preflight(self, request: TestExecutionRequest) -> None:
        """Check source with the worker's pinned Playwright runtime before dispatch."""
        body = json.dumps(request.model_dump(mode="json")).encode()
        try:
            with urlopen(
                Request(
                    f"{self._url.removesuffix('/execute')}/preflight",
                    data=body,
                    headers={"Content-Type": "application/json"},
                ),
                timeout=15,
            ) as response:
                payload = json.loads(response.read())
            if not isinstance(payload, dict) or payload.get("accepted") is not True:
                raise RunnerUnavailableError("generated source failed Playwright preflight")
        except (HTTPError, TimeoutError, URLError, ValueError, json.JSONDecodeError) as error:
            raise RunnerUnavailableError(
                "generated source Playwright preflight is unavailable"
            ) from error

    def cancel(self, run_id: str) -> None:
        """Notify the worker that a durable cancellation reached an active run.

        The endpoint is deliberately idempotent: a worker may receive this more
        than once when the outbox publisher retries an unacknowledged delivery.
        """
        body = json.dumps({"run_id": run_id}).encode()
        try:
            with urlopen(
                Request(
                    f"{self._url.removesuffix('/execute')}/cancel",
                    data=body,
                    headers={"Content-Type": "application/json"},
                ),
                timeout=self._timeout_seconds,
            ):
                return
        except (HTTPError, URLError, TimeoutError) as error:
            raise RunnerUnavailableError(
                "Playwright worker cancellation was not acknowledged"
            ) from error


class VerifiedLocalArtifactPort:
    """Accept only evidence inside the shared root whose reported digest matches bytes."""

    def __init__(self, root: str, repository: ArtifactRepository | None = None) -> None:
        self._root = Path(root).resolve()
        self._repository = repository

    def persist_result_artifacts(
        self, tenant_id: str, result: TestExecutionResult, retain_days: int
    ) -> None:
        evidence = result.runner_metadata.get("evidence", {})
        if not isinstance(evidence, dict):
            raise ValueError("runner evidence manifest is invalid")
        for artifact in result.artifacts:
            if not artifact.uri.startswith("file://"):
                raise ValueError("local artifact URI is invalid")
            path = self._path_for_uri(artifact.uri)
            if self._root not in path.parents or not path.is_file():
                raise ValueError("artifact is outside the configured root")
            metadata = evidence.get(artifact.uri)
            if not isinstance(metadata, dict):
                raise ValueError("artifact checksum metadata is missing")
            content = path.read_bytes()
            checksum = hashlib.sha256(content).hexdigest()
            if metadata.get("checksum") != checksum or metadata.get("size") != len(content):
                raise ValueError("artifact checksum verification failed")
            if self._repository is None:
                raise RuntimeError("artifact repository is required for persistence")
            self._repository.add(
                ArtifactRecord(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    run_id=result.run_id,
                    kind=artifact.kind,
                    uri=artifact.uri,
                    checksum=checksum,
                    size=len(content),
                    content_type=artifact.content_type,
                    retention_until=datetime.now(UTC) + timedelta(days=retain_days),
                )
            )

    def verified_path(self, artifact: ArtifactRecord) -> Path:
        path = self._path_for_uri(artifact.uri)
        if (
            not artifact.uri.startswith("file://")
            or self._root not in path.parents
            or not path.is_file()
        ):
            raise ValueError("artifact URI is invalid")
        if hashlib.sha256(path.read_bytes()).hexdigest() != artifact.checksum:
            raise ValueError("artifact checksum verification failed")
        return path

    def read_verified_bytes(self, artifact: ArtifactRecord, max_bytes: int) -> bytes:
        """Return a capped artifact only after its stored checksum is verified."""
        if artifact.size > max_bytes:
            raise ValueError("artifact exceeds the configured raw-byte cap")
        return self.verified_path(artifact).read_bytes()

    @staticmethod
    def _path_for_uri(uri: str) -> Path:
        parsed = urlparse(uri)
        if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
            raise ValueError("artifact URI is invalid")
        value = unquote(parsed.path)
        if len(value) >= 3 and value[0] == "/" and value[2] == ":":
            value = value[1:]
        return Path(value).resolve()


class VerifiedArtifactPromotion:
    """Promotes verified worker staging files without granting workers storage credentials."""

    def __init__(
        self,
        root: str,
        repository: ArtifactRepository,
        store: RustFSArtifactStore,
        max_upload_bytes: int = 100_000_000,
    ) -> None:
        self._local = VerifiedLocalArtifactPort(root)
        self._repository = repository
        self._store = store
        self._max_upload_bytes = max_upload_bytes

    def persist_result_artifacts(
        self, tenant_id: str, result: TestExecutionResult, retain_days: int
    ) -> None:
        evidence = result.runner_metadata.get("evidence", {})
        if not isinstance(evidence, dict):
            raise ValueError("runner evidence manifest is invalid")
        promoted: list[Path] = []
        records: list[ArtifactRecord] = []
        for artifact in result.artifacts:
            path = self._local._path_for_uri(artifact.uri)
            if self._local._root not in path.parents or not path.is_file():
                raise ValueError("artifact is outside the configured root")
            metadata = evidence.get(artifact.uri)
            content = path.read_bytes()
            if len(content) > self._max_upload_bytes:
                raise ValueError("artifact exceeds the configured upload cap")
            checksum = hashlib.sha256(content).hexdigest()
            if (
                not isinstance(metadata, dict)
                or metadata.get("checksum") != checksum
                or metadata.get("size") != len(content)
            ):
                raise ValueError("artifact checksum verification failed")
            safe_kind = "".join(
                char if char.isalnum() or char in "-_" else "-" for char in artifact.kind
            )
            suffix = "".join(
                char for char in path.suffix.lower() if char.isalnum() or char == "."
            )[:16]
            key = (
                f"tenants/{tenant_id}/runs/{result.run_id}/artifacts/"
                f"{safe_kind}-{checksum[:12]}{suffix}"
            )
            uri = self._store.put_verified(key, content, checksum, artifact.content_type)
            records.append(
                ArtifactRecord(
                    uuid4(),
                    tenant_id,
                    result.run_id,
                    artifact.kind,
                    uri,
                    checksum,
                    len(content),
                    artifact.content_type,
                    datetime.now(UTC) + timedelta(days=retain_days),
                )
            )
            promoted.append(path)
        for record in records:
            self._repository.add(record)
        for path in promoted:
            path.unlink(missing_ok=True)
