"""API document-to-pipeline-contract conversion endpoint."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.v1.deps import require_not_dev
from app.config import settings
from app.services.api_spec_conversion_service import (
    APISpecConversionResult,
    convert_api_document,
)
from app.tools.document_parser import parse_document, supported_extensions

router = APIRouter()


def _validate_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Base URL must be an absolute http(s) URL.",
        )
    return normalized


@router.post(
    "/spec-conversions",
    response_model=APISpecConversionResult,
    summary="Convert an API document to the pipeline Markdown contract",
)
async def convert_pipeline_spec(
    file: Annotated[UploadFile, File(description="Source API document")],
    base_url: Annotated[str, Form(description="Runtime API base URL")],
    llm_profile_id: Annotated[str | None, Form()] = None,
    _: object = Depends(require_not_dev),
) -> APISpecConversionResult:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in set(supported_extensions()):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported source format {suffix!r}.",
        )

    raw = await file.read(settings.max_file_size_bytes + 1)
    if len(raw) > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.MAX_FILE_SIZE_MB} MB.",
        )

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(raw)
            temp_path = Path(temp_file.name)
        source_text = await asyncio.to_thread(parse_document, temp_path)
        return await convert_api_document(
            source_text,
            source_name=file.filename or "api-document",
            base_url=_validate_base_url(base_url),
            llm_profile_id=llm_profile_id,
        )
    except HTTPException:
        raise
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Document conversion timed out.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Document conversion failed: {exc}") from exc
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
