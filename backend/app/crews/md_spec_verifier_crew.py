"""
crews/md_spec_verifier_crew.py
──────────────────────────────
Pure-Python guard crew for the Automation Testing API pipeline.

Responsibilities:
  1. Take the raw MD content (already parsed by ``parse_document``) or
     a ``file_path`` and run it through
     :func:`~app.tools.md_api_spec_validator.validate_md_api_spec`.
  2. Raise :class:`~app.core.errors.MDSpecValidationError` when the spec
     is invalid in strict mode — the :class:`DAGPipelineRunner` will
     detect the structured error type and skip retry.
  3. Forward ``parsed`` (endpoint / request / responses) downstream so
     other nodes (test_case_generator, test_level_classifier, ...) can
     reuse it without re-parsing.

Registered as a builtin pure-Python node handler in
``DAGPipelineRunner._run_pure_python_node`` under the agent_id
``"md_api_spec_verifier"``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from app.core.errors import MDSpecValidationError
from app.crews.base_crew import BaseCrew, ProgressCallback
from app.tools.md_api_spec_validator import (
    ValidationResult,
    to_summary,
    validate_md_api_spec,
)

logger = logging.getLogger(__name__)


class MDSpecVerifierCrew(BaseCrew):
    """Validate an uploaded MD API spec before the rest of the DAG runs."""

    stage = "ingestion"
    agent_ids: list[str] = ["md_api_spec_verifier"]

    def __init__(
        self,
        run_id: str,
        run_profile_id: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
        mock_mode: Optional[bool] = None,
        **_kwargs: Any,
    ) -> None:
        super().__init__(
            run_id=run_id,
            run_profile_id=run_profile_id,
            progress_callback=progress_callback,
            mock_mode=mock_mode,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ─────────────────────────────────────────────────────────────────────────

    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:  # noqa: D401
        """Validate the MD spec and forward parsed sections downstream.

        Args:
            input_data: Dict with one of:
                - ``document_content`` (str): pre-parsed MD text (preferred).
                - ``file_path`` (str | Path): absolute path to the ``.md`` file.
                Optional keys:
                - ``strict`` (bool, default True)
                - ``md_spec_synonyms`` (dict[str, list[str]])

        Returns:
            ``dict`` shaped as::

                {
                    "md_spec_valid": True,
                    "md_spec_parsed": { ... ParsedSpec dump ... },
                    "md_spec_warnings": [ ... ],
                    "document_content": "<raw md text>",
                    "document_name":    "<name>",
                }

        Raises:
            MDSpecValidationError: When strict=True and the spec violates the
                contract. The DAG runner detects this class and marks the run
                as failed without retry.
        """
        self._emit_agent_started(
            "md_api_spec_verifier", "MD API Spec Verifier"
        )

        text = self._load_text(input_data)
        strict = input_data.get("strict_md_spec", input_data.get("strict", True))
        if not isinstance(strict, bool):
            strict = True
        synonyms = input_data.get("md_spec_synonyms") or None

        result: ValidationResult = validate_md_api_spec(
            text, strict=strict, extra_synonyms=synonyms
        )

        self._emit(
            "log",
            {
                "message": f"MD spec validation: {to_summary(result)}",
                "level": "info" if result.valid else "error",
            },
        )

        if not result.valid:
            self._emit_agent_failed(
                "md_api_spec_verifier",
                f"{result.code}: {result.detail}",
            )
            logger.warning(
                "[MDSpecVerifier][%s] invalid spec: code=%s detail=%s",
                self._run_id,
                result.code,
                result.detail,
            )
            raise MDSpecValidationError(
                code=result.code or "MD_SPEC_VALIDATION_FAILED",
                detail=result.detail or "MD spec failed validation.",
                missing_sections=result.missing_sections,
                missing_fields=result.missing_fields,
                field_errors=[item.model_dump() for item in result.field_errors],
            )

        self._emit_agent_completed(
            "md_api_spec_verifier",
            output_preview=(
                f"valid · {result.parsed.endpoint.method} "
                f"{result.parsed.endpoint.path} · "
                f"{len(result.parsed.responses)} response(s)"
            ),
        )

        document_name = input_data.get("document_name") or ""
        return {
            "md_spec_valid": True,
            "md_spec_parsed": result.parsed.model_dump(),
            "md_spec_warnings": list(result.warnings),
            "document_content": text,
            "document_name": document_name,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _load_text(self, input_data: dict[str, Any]) -> str:
        preloaded = input_data.get("document_content") or ""
        if preloaded:
            return preloaded

        file_path = input_data.get("file_path")
        if not file_path:
            raise MDSpecValidationError(
                code="MD_SPEC_MISSING_ENDPOINT",
                detail=(
                    "No document_content or file_path provided to "
                    "md_api_spec_verifier."
                ),
                missing_sections=["endpoint", "request", "response"],
            )

        path = Path(file_path)
        if not path.exists():
            raise MDSpecValidationError(
                code="MD_SPEC_MISSING_ENDPOINT",
                detail=f"MD spec file not found: {path}",
            )

        if path.suffix.lower() not in (".md", ".markdown"):
            raise MDSpecValidationError(
                code="MD_SPEC_MISSING_ENDPOINT",
                detail=(
                    f"Uploaded file '{path.name}' is not a Markdown file. "
                    "The Automation Testing API pipeline only accepts .md / .markdown."
                ),
            )

        return path.read_text(encoding="utf-8")
