"""
crews/api_test_runner_crew.py
─────────────────────────────
Pure-Python crew that executes API test cases via httpx.

Replaces the LLM-driven ``test_runner`` agent in the
``automation-testing-api`` pipeline. The previous CrewAI agent expected
the LLM to follow a multi-step protocol (call ``api_runner`` tool, build
a JSON of results, return a summary) — a weak local model could not
emit the required ``results`` array reliably.

This crew is a deterministic loop over the upstream ``test_cases``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.crews.base_crew import BaseCrew, ProgressCallback
from app.tools.api_test_runner import execute_test_cases

logger = logging.getLogger(__name__)


class ApiTestRunnerCrew(BaseCrew):
    """Execute every executable TestCase via httpx."""

    stage = "execution"
    agent_ids: list[str] = ["api_test_runner"]

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
        """Execute every executable case and emit an ExecutionOutput dict.

        Args:
            input_data: Merged DAG input. Expected keys:
                - ``test_cases`` (list[dict]) — from the rule-based
                  generator + test_level_classifier.
                - ``document_content`` (str)  — used to recover the
                  ``Base URL`` for live execution.

        Returns:
            ``ExecutionOutput.model_dump()`` dict.
        """
        self._emit_agent_started("api_test_runner", "API Test Runner")

        test_cases = list(input_data.get("test_cases") or [])
        document_content = str(input_data.get("document_content") or "")

        # Source of truth for the base URL is the already-validated parsed spec
        # (it accepts the bullet `- Base URL:` form); fall back to scraping the
        # raw document only when the parsed spec is unavailable.
        parsed_spec = input_data.get("md_spec_parsed")
        base_url_override = (
            (parsed_spec.get("base_url") or None)
            if isinstance(parsed_spec, dict)
            else None
        )

        if not test_cases:
            self._emit_log(
                "No test cases received — emitting empty execution output.",
                level="warning",
            )
            self._emit_agent_completed(
                "api_test_runner", output_preview="no test cases"
            )
            return {
                "results": [],
                "summary": {
                    "total": 0, "passed": 0, "failed": 0,
                    "skipped": 0, "errors": 0, "pass_rate": 0.0,
                    "duration_seconds": 0.0,
                },
            }

        self._emit_log(
            "Base URL resolved from "
            + ("parsed spec" if base_url_override else "document")
            + f": {base_url_override or '(scraped at runtime)'}",
            level="info",
        )
        output = execute_test_cases(
            test_cases=test_cases,
            document_content=document_content,
            base_url_override=base_url_override,
        )

        summary = output.summary
        self._emit_log(
            f"Executed {summary.total} case(s) — "
            f"passed={summary.passed} failed={summary.failed} "
            f"skipped={summary.skipped} errors={summary.errors}",
            level="info",
        )
        self._emit_agent_completed(
            "api_test_runner",
            output_preview=(
                f"{summary.total} result(s) · pass_rate={summary.pass_rate}%"
            ),
        )

        return output.model_dump()
