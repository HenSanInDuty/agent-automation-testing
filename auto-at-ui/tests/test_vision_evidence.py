import hashlib
from uuid import uuid4

import pytest
from agents.vision.evidence import VerifiedScreenshotReader
from domain.entities import ArtifactRecord


class BytesReader:
    def __init__(self, value: bytes) -> None:
        self.value = value

    def read_verified_bytes(self, artifact: ArtifactRecord, max_bytes: int) -> bytes:
        assert artifact.size <= max_bytes
        return self.value


def screenshot(*, tenant_id: str = "tenant-a", run_id=None, content: bytes | None = None):
    image = content if content is not None else b"\x89PNG\r\n\x1a\nimage"
    return ArtifactRecord(
        id=uuid4(), tenant_id=tenant_id, run_id=run_id or uuid4(), kind="screenshot",
        uri="file:///private/screenshot.png", checksum=hashlib.sha256(image).hexdigest(),
        size=len(image), content_type="image/png",
    )


def test_verified_screenshot_reader_returns_only_bounded_metadata_and_bytes() -> None:
    artifact = screenshot()
    metadata, raw = VerifiedScreenshotReader(BytesReader(b"\x89PNG\r\n\x1a\nimage")).read(
        tenant_id="tenant-a", run_id=artifact.run_id, session_id=uuid4(), artifact=artifact,
        max_bytes=1_000,
    )

    assert raw.startswith(b"\x89PNG")
    assert metadata.artifact_id == artifact.id
    assert "file:" not in metadata.model_dump_json()


@pytest.mark.parametrize(
    ("artifact_tenant", "run_matches", "content_type", "content", "max_bytes"),
    [
        ("tenant-b", True, "image/png", b"\x89PNG\r\n\x1a\nimage", 1_000),
        ("tenant-a", False, "image/png", b"\x89PNG\r\n\x1a\nimage", 1_000),
        ("tenant-a", True, "text/plain", b"\x89PNG\r\n\x1a\nimage", 1_000),
        ("tenant-a", True, "image/png", b"not-an-image", 1_000),
        ("tenant-a", True, "image/png", b"\x89PNG\r\n\x1a\nimage", 1),
    ],
)
def test_verified_screenshot_reader_rejects_invalid_scope_or_content(
    artifact_tenant, run_matches, content_type, content, max_bytes
) -> None:
    expected_run = uuid4()
    artifact = screenshot(
        tenant_id=artifact_tenant,
        run_id=expected_run if run_matches else uuid4(),
        content=content,
    )
    artifact = ArtifactRecord(**{**artifact.__dict__, "content_type": content_type})

    with pytest.raises(ValueError):
        VerifiedScreenshotReader(BytesReader(content)).read(
            tenant_id="tenant-a", run_id=expected_run, session_id=uuid4(), artifact=artifact,
            max_bytes=max_bytes,
        )
