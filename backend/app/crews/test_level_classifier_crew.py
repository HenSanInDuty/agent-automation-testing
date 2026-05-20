"""
crews/test_level_classifier_crew.py
───────────────────────────────────
Pure-Python crew that tags every TestCase with ``test_level`` + ``executable``.

Sits between ``test_case_generator`` and ``automation_agent`` in the
Automation Testing API DAG. Uses :mod:`app.tools.test_level_tagger` rule-first;
emits warnings for low-confidence cases but never blocks the pipeline.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.crews.base_crew import BaseCrew, ProgressCallback
from app.schemas.pipeline_io import TestCaseOutput, TestLevel
from app.tools.test_level_tagger import classify_test_level, needs_llm_fallback

logger = logging.getLogger(__name__)


class TestLevelClassifierCrew(BaseCrew):
    """Tag each TestCase with test_level + executable flag."""

    stage = "testcase"
    agent_ids: list[str] = ["test_level_classifier"]

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
        """Annotate every case in ``input_data['test_cases']`` (in-place).

        Args:
            input_data: Merged DAG input. Expected keys:
                - ``test_cases`` (list[dict]) — from test_case_generator.
                - ``md_spec_parsed`` (dict)    — from md_api_spec_verifier
                                                 (contains ``endpoint``).

        Returns:
            Dict mirroring the upstream :class:`TestCaseOutput` schema with
            ``test_level`` + ``executable`` populated, plus a small
            classification summary.
        """
        self._emit_agent_started(
            "test_level_classifier", "Test Level Classifier"
        )

        test_cases: list[dict[str, Any]] = list(input_data.get("test_cases") or [])
        endpoint_hint: Optional[dict[str, Any]] = None
        parsed_spec = input_data.get("md_spec_parsed") or {}
        if isinstance(parsed_spec, dict):
            endpoint_hint = parsed_spec.get("endpoint") or None

        level_counts: dict[str, int] = {}
        low_confidence: list[str] = []
        executable_count = 0

        for tc in test_cases:
            level, executable, confidence = classify_test_level(tc, endpoint_hint)
            tc["test_level"] = level.value
            tc["executable"] = bool(executable)
            tc["classification_confidence"] = round(confidence, 3)

            level_counts[level.value] = level_counts.get(level.value, 0) + 1
            if executable:
                executable_count += 1
            if needs_llm_fallback(confidence):
                low_confidence.append(str(tc.get("id", "TC-?")))

        summary = {
            "by_level": level_counts,
            "executable_count": executable_count,
            "skipped_count": len(test_cases) - executable_count,
            "low_confidence_ids": low_confidence,
        }

        self._emit_log(
            f"Classified {len(test_cases)} test case(s) — "
            f"executable={executable_count}, "
            f"low_conf={len(low_confidence)}",
            level="info",
        )
        self._emit_agent_completed(
            "test_level_classifier",
            output_preview=f"by_level={level_counts}",
        )

        # Forward the full upstream payload + augmented test_cases so
        # downstream nodes do not lose context.
        out = dict(input_data)
        out["test_cases"] = test_cases
        out["total_test_cases"] = len(test_cases)
        out["classification_summary"] = summary

        # Best-effort: keep upstream TestCaseOutput model_validate happy
        try:
            tco = TestCaseOutput.model_validate(
                {
                    "test_cases": test_cases,
                    "total_test_cases": len(test_cases),
                    "coverage_summary": input_data.get("coverage_summary") or {},
                    "automation_readiness": input_data.get("automation_readiness")
                    or {},
                    "design_notes": input_data.get("design_notes") or [],
                    "risks": input_data.get("risks") or [],
                    "recommendations": input_data.get("recommendations") or [],
                }
            )
            out["testcase_output"] = tco.model_dump()
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "[TestLevelClassifier][%s] Could not validate upstream "
                "TestCaseOutput: %s (continuing anyway)",
                self._run_id,
                exc,
            )

        # Ensure default level present (helps downstream defensive code)
        out.setdefault("default_test_level", TestLevel.UNIT.value)
        return out
