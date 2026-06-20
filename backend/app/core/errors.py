"""
core/errors.py
──────────────
Structured pipeline error classes.

These exceptions carry machine-readable metadata so the DAG runner can
serialize them into ``PipelineRunDocument.error_message`` JSON and so the
frontend can render section-level guidance instead of stack traces.

Currently defined:
  - MDSpecValidationError       — thrown by the md_api_spec_verifier
                                  guard node when an uploaded ``.md`` file
                                  does not meet the contract in
                                  ``docs/Flow/automation-testing-api-md-contract.md``.
  - ReportVerificationError     — thrown by the report_verifier guard
                                  when the final HTML/DOCX report is
                                  missing one of the 3 required
                                  components (test cases / results /
                                  unit test files).

All structured errors expose ``.to_dict()`` for JSON serialization.
"""

from __future__ import annotations

import json
from typing import Any


class StructuredPipelineError(Exception):
    """Base class for pipeline errors that carry structured metadata."""

    error_type: str = "pipeline_error"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable summary of the error."""
        return {"error_type": self.error_type, "detail": str(self)}

    def __str__(self) -> str:  # noqa: D401
        return json.dumps(self.to_dict(), ensure_ascii=False)


class MDSpecValidationError(StructuredPipelineError):
    """Raised when an uploaded MD API spec violates the v1 contract.

    Attributes:
        code:             Stable machine code (see contract §5), e.g.
                          ``"MD_SPEC_MISSING_ENDPOINT"``.
        missing_sections: H2 section names that the validator failed to find.
        missing_fields:   Required field/key names that were absent.
        detail:           Human-readable explanation (also used as exc message).
    """

    error_type: str = "md_spec_validation"

    def __init__(
        self,
        code: str,
        detail: str,
        *,
        missing_sections: list[str] | None = None,
        missing_fields: list[str] | None = None,
        field_errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.missing_sections = list(missing_sections or [])
        self.missing_fields = list(missing_fields or [])
        self.field_errors = list(field_errors or [])

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.error_type,
            "code": self.code,
            "missing_sections": self.missing_sections,
            "missing_fields": self.missing_fields,
            "field_errors": self.field_errors,
            "detail": self.detail,
        }


class ReportVerificationError(StructuredPipelineError):
    """Raised when the final report fails the 3-component verification.

    Attributes:
        components: Mapping ``{component_name: {"ok": bool, "issues": [...]}}``
        detail:     Human-readable summary.
    """

    error_type: str = "report_verification"

    def __init__(
        self,
        detail: str,
        *,
        components: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.components = dict(components or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.error_type,
            "detail": self.detail,
            "components": self.components,
        }


def is_structured_pipeline_error(exc: BaseException) -> bool:
    """Return True if *exc* is a structured pipeline error.

    The DAG runner uses this check to bypass retry on fail-fast errors
    (validation failures, contract violations, ...) which would never be
    fixed by simply retrying.
    """
    return isinstance(exc, StructuredPipelineError)
