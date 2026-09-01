import hashlib
from uuid import uuid4

import pytest
from auto_at.contracts.execution import Artifact, RunStatus
from auto_at.contracts.execution import TestExecutionResult as ExecutionResult
from domain.entities import ArtifactRecord
from infrastructure.runners import VerifiedArtifactPromotion, VerifiedLocalArtifactPort


class InMemoryArtifacts:
    def __init__(self) -> None:
        self.items: list[ArtifactRecord] = []

    def add(self, artifact: ArtifactRecord) -> None:
        self.items.append(artifact)


class Store:
    def __init__(self) -> None:
        self.items: dict[str, bytes] = {}

    def put_verified(
        self, key: str, content: bytes, checksum: str, _content_type: str | None
    ) -> str:
        assert hashlib.sha256(content).hexdigest() == checksum
        self.items[key] = content
        return f"s3://artifacts/{key}"


def make_result(uri: str, checksum: str, size: int) -> ExecutionResult:
    return ExecutionResult(
        run_id=uuid4(),
        correlation_id=uuid4(),
        status=RunStatus.FAILED,
        started_at="2026-07-22T00:00:00Z",
        completed_at="2026-07-22T00:00:01Z",
        summary="Expected failure.",
        artifacts=[Artifact(kind="screenshot", uri=uri, content_type="image/png")],
        runner_metadata={"evidence": {uri: {"checksum": checksum, "size": size}}},
    )


def test_verified_artifact_port_persists_only_matching_evidence(tmp_path) -> None:
    root = tmp_path / "artifacts"
    artifact_path = root / "run-1" / "screen.png"
    artifact_path.parent.mkdir(parents=True)
    bytes_ = b"evidence bytes"
    artifact_path.write_bytes(bytes_)
    uri = artifact_path.resolve().as_uri()
    repository = InMemoryArtifacts()
    result = make_result(uri, hashlib.sha256(bytes_).hexdigest(), len(bytes_))

    VerifiedLocalArtifactPort(str(root), repository).persist_result_artifacts(
        "tenant-a", result, 30
    )

    assert repository.items[0].checksum == hashlib.sha256(bytes_).hexdigest()
    assert repository.items[0].content_type == "image/png"
    assert VerifiedLocalArtifactPort(str(root)).verified_path(repository.items[0]) == artifact_path


def test_verified_artifact_port_rejects_a_bad_checksum(tmp_path) -> None:
    root = tmp_path / "artifacts"
    artifact_path = root / "run-1" / "screen.png"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"evidence bytes")
    result = make_result(artifact_path.resolve().as_uri(), "0" * 64, 14)

    with pytest.raises(ValueError, match="checksum"):
        VerifiedLocalArtifactPort(str(root), InMemoryArtifacts()).persist_result_artifacts(
            "tenant-a", result, 30
        )


def test_promotion_persists_s3_metadata_only_after_verified_upload_and_clears_staging(
    tmp_path,
) -> None:
    root = tmp_path / "artifacts"
    artifact_path = root / "run-1" / "screen.png"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"evidence bytes")
    repository, store = InMemoryArtifacts(), Store()
    result = make_result(
        artifact_path.resolve().as_uri(), hashlib.sha256(b"evidence bytes").hexdigest(), 14
    )

    VerifiedArtifactPromotion(str(root), repository, store).persist_result_artifacts(
        "tenant-a", result, 30
    )

    assert repository.items[0].uri.startswith(
        f"s3://artifacts/tenants/tenant-a/runs/{result.run_id}/"
    )
    assert store.items and not artifact_path.exists()
