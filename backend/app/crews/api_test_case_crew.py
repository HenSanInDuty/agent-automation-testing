"""
crews/api_test_case_crew.py
───────────────────────────
Pure-Python crew that generates API test cases from the parsed MD spec.

Replaces the LLM-driven ``test_case_generator`` agent in the
``automation-testing-api`` pipeline when a weak LLM (e.g. a small local
Ollama model) cannot reliably emit the ``test_cases`` JSON schema.

The crew is a thin orchestration layer around
:func:`app.tools.api_test_case_generator.generate_test_cases` — it owns
the progress events, agent lifecycle, and unwrapping of the parsed spec
into a :class:`~app.tools.md_api_spec_validator.ParsedSpec`.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.crews.base_crew import BaseCrew, ProgressCallback
from app.tools.api_test_case_generator import generate_test_cases
from app.tools.md_api_spec_validator import ParsedSpec

logger = logging.getLogger(__name__)


class ApiTestCaseCrew(BaseCrew):
    """Generate API test cases deterministically from the parsed MD spec."""

    stage = "testcase"
    agent_ids: list[str] = ["api_test_case_generator"]

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
        """Build :class:`TestCaseOutput` from ``md_spec_parsed``.

        Args:
            input_data: Merged DAG input. Expected keys:
                - ``md_spec_parsed`` (dict): from ``md_api_spec_verifier``.
                - ``document_content`` (str): retained for compatibility;
                  normalized URL and headers come from ``md_spec_parsed``.
                - ``requirements`` (list[dict], optional): used purely for
                  traceability — the first ``id`` is attached to every
                  generated test case.

        Returns:
            ``TestCaseOutput.model_dump()`` dict.
        """
        self._emit_agent_started(
            "api_test_case_generator", "API Test Case Generator"
        )

        parsed_dict = input_data.get("md_spec_parsed") or {}
        if not parsed_dict:
            self._emit_log(
                "md_spec_parsed missing from input — emitting empty test suite.",
                level="warning",
            )
            self._emit_agent_completed(
                "api_test_case_generator", output_preview="no parsed spec"
            )
            return {"test_cases": [], "total_test_cases": 0}

        try:
            parsed = ParsedSpec.model_validate(parsed_dict)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[ApiTestCase][%s] Failed to coerce md_spec_parsed: %s",
                self._run_id,
                exc,
            )
            self._emit_log(
                f"Could not coerce md_spec_parsed into ParsedSpec ({exc}); "
                "emitting empty test suite.",
                level="warning",
            )
            self._emit_agent_completed(
                "api_test_case_generator",
                output_preview="parsed-spec coercion failed",
            )
            return {"test_cases": [], "total_test_cases": 0}

        document_content = str(input_data.get("document_content") or "")
        requirement_ids = [
            str(r.get("id"))
            for r in (input_data.get("requirements") or [])
            if isinstance(r, dict) and r.get("id")
        ]

        output = generate_test_cases(
            parsed=parsed,
            document_content=document_content,
            requirement_ids=requirement_ids,
        )

        endpoint_count = len(parsed.endpoints)
        self._emit_log(
            f"Rule-based generator produced {output.total_test_cases} "
            f"test case(s) across {endpoint_count} endpoint(s).",
            level="info",
        )
        self._emit_agent_completed(
            "api_test_case_generator",
            output_preview=(
                f"{output.total_test_cases} case(s) · "
                f"{endpoint_count} endpoint(s)"
            ),
        )

        return output.model_dump()
