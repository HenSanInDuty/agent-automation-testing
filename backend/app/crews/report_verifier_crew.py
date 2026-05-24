"""
crews/report_verifier_crew.py
─────────────────────────────
Pure-Python guard crew that verifies the final report carries all 3
mandatory components (test cases / results / unit test files) before
the user downloads it.

Raises :class:`~app.core.errors.ReportVerificationError` when verification
fails; the :class:`DAGPipelineRunner` detects the structured error and
marks the run as failed without retry.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.errors import ReportVerificationError
from app.crews.base_crew import BaseCrew, ProgressCallback
from app.tools.report_verifier import verify_report

logger = logging.getLogger(__name__)


class ReportVerifierCrew(BaseCrew):
    stage = "reporting"
    agent_ids: list[str] = ["report_verifier"]

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

    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        self._emit_agent_started("report_verifier", "Report Verifier")

        test_cases = (
            input_data.get("test_cases")
            or (input_data.get("testcase_output") or {}).get("test_cases")
            or []
        )
        results = (
            input_data.get("results")
            or (input_data.get("execution_output") or {}).get("results")
            or []
        )
        unit_test_files = (
            input_data.get("unit_test_files")
            or (input_data.get("artifact_output") or {}).get("unit_test_files")
            or []
        )
        # Use explicit `is not None` lookup — `or`-chains treat
        # ``pass_rate == 0.0`` as falsy and would mark it as missing.
        _summary = input_data.get("summary")
        if not isinstance(_summary, dict):
            _summary = (
                (input_data.get("execution_output") or {}).get("summary") or {}
            )
        pass_rate = _summary.get("pass_rate") if isinstance(_summary, dict) else None

        result = verify_report(
            test_cases=test_cases,
            results=results,
            unit_test_files=unit_test_files,
            pass_rate=pass_rate,
            html_bytes=input_data.get("_html_bytes") or b"",
            docx_bytes=input_data.get("_docx_bytes") or b"",
            html_url=input_data.get("html_path") or "",
            docx_url=input_data.get("docx_path") or "",
        )

        components_dump = {k: v.model_dump() for k, v in result.components.items()}
        verification_payload: dict[str, Any] = {
            "verified": result.verified,
            "components": components_dump,
            "html_url": result.html_url,
            "docx_url": result.docx_url,
            "summary": result.summary,
        }

        if not result.verified:
            self._emit_agent_failed(
                "report_verifier",
                f"Verification failed: {result.summary}",
            )
            logger.warning(
                "[ReportVerifier][%s] failed: components=%s",
                self._run_id,
                components_dump,
            )
            raise ReportVerificationError(
                detail=result.summary,
                components=components_dump,
            )

        self._emit_agent_completed(
            "report_verifier",
            output_preview=(
                f"verified · tc={result.components['test_cases'].count} "
                f"results={result.components['results'].count} "
                f"unit_files={result.components['unit_test_files'].count}"
            ),
        )

        out = dict(input_data)
        out["report_verification"] = verification_payload
        # Strip raw bytes — they should not be persisted in PipelineResultDocument.
        out.pop("_html_bytes", None)
        out.pop("_docx_bytes", None)
        return out
