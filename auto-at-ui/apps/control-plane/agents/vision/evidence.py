"""Verified, transient screenshot access for the vision adapter only."""

from typing import Protocol
from uuid import UUID

from auto_at.contracts.vision import VisualEvidenceMetadata
from domain.entities import ArtifactRecord


class VerifiedArtifactReader(Protocol):
    def read_verified_bytes(self, artifact: ArtifactRecord, max_bytes: int) -> bytes: ...


class VerifiedScreenshotReader:
    """Read one allowlisted screenshot after tenant/run/session checks.

    The caller supplies an artifact selected through its tenant- and
    session-scoped workflow. Bytes are returned only transiently and this
    boundary never produces a URI or a serializable evidence payload.
    """

    def __init__(self, reader: VerifiedArtifactReader) -> None:
        self._reader = reader

    def read(
        self,
        *,
        tenant_id: str,
        run_id: UUID,
        session_id: UUID,
        artifact: ArtifactRecord,
        max_bytes: int,
    ) -> tuple[VisualEvidenceMetadata, bytes]:
        if not tenant_id or session_id is None:
            raise ValueError("visual screenshot scope is invalid")
        if artifact.tenant_id != tenant_id or artifact.run_id != run_id:
            raise ValueError("screenshot is outside the visual exploration scope")
        if artifact.kind != "screenshot":
            raise ValueError("visual evidence must be a screenshot artifact")
        if artifact.size > max_bytes:
            raise ValueError("screenshot exceeds the configured raw-byte cap")
        content_type = (artifact.content_type or "").lower()
        if content_type not in {"image/png", "image/jpeg"}:
            raise ValueError("screenshot content type is not allowed")
        content = self._reader.read_verified_bytes(artifact, max_bytes)
        if len(content) != artifact.size:
            raise ValueError("screenshot declared size does not match verified bytes")
        if not _has_expected_image_signature(content, content_type):
            raise ValueError("screenshot bytes do not match the declared image type")
        return (
            VisualEvidenceMetadata(
                artifact_id=artifact.id,
                checksum=artifact.checksum,
                content_type=content_type,
                byte_count=len(content),
            ),
            content,
        )


def _has_expected_image_signature(content: bytes, content_type: str) -> bool:
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    return len(content) >= 4 and content.startswith(b"\xff\xd8") and content.endswith(b"\xff\xd9")
