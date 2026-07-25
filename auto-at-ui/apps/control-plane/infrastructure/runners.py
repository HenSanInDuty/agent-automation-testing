"""Replaceable local transport and verified local artifact port for Phase 2."""

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from auto_at.contracts.execution import TestExecutionRequest, TestExecutionResult
from domain.entities import ArtifactRecord
from domain.ports import ArtifactRepository

logger = logging.getLogger(__name__)


class RunnerUnavailableError(RuntimeError):
    pass


class HttpPlaywrightTransport:
    """The local HTTP boundary can be replaced by a durable workflow transport."""

    def __init__(self, worker_url: str, timeout_seconds: float = 90) -> None:
        self._url = f"{worker_url.rstrip('/')}/execute"
        self._timeout_seconds = timeout_seconds

    def execute(self, request: TestExecutionRequest) -> TestExecutionResult:
        body = json.dumps(request.model_dump(mode="json")).encode()
        try:
            with urlopen(
                Request(self._url, data=body, headers={"Content-Type": "application/json"}),
                timeout=self._timeout_seconds,
            ) as response:
                return TestExecutionResult.model_validate_json(response.read())
        except TimeoutError as error:
            logger.warning(
                "run.timeout run_id=%s correlation_id=%s timeout_seconds=%s",
                request.run_id,
                request.correlation_id,
                self._timeout_seconds,
            )
            raise RunnerUnavailableError("Playwright worker timed out") from error
        except (URLError, ValueError) as error:
            raise RunnerUnavailableError(
                "Playwright worker did not return a valid result"
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

    @staticmethod
    def _path_for_uri(uri: str) -> Path:
        parsed = urlparse(uri)
        if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
            raise ValueError("artifact URI is invalid")
        value = unquote(parsed.path)
        if len(value) >= 3 and value[0] == "/" and value[2] == ":":
            value = value[1:]
        return Path(value).resolve()
