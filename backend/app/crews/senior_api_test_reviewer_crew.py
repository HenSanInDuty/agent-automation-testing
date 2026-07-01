"""
crews/senior_api_test_reviewer_crew.py
─────────────────────────────────────────
Senior qualitative reviewer for the adaptive coverage gate.

One senior agent assesses a consolidated plan for correctness, contradictions,
unsafe assumptions, executability, and missing edge cases, then returns a strict
JSON verdict (``approve|revise|reject``) with evidence, gaps, and targeted
feedback for the next planning iteration.

The reviewer is **advisory**: it may reject a plan but can never fabricate the
numeric coverage that the deterministic gate owns. When the reviewer is mocked,
times out, or returns invalid output, :meth:`review` produces a deterministic
coverage-only fallback verdict (``fallback=True``) and never triggers an
unbounded retry — the bounded loop stays in control.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from app.crews.base_crew import BaseCrew, ProgressCallback
from app.schemas.pipeline_io import (
    CoverageReport,
    ReviewVerdict,
    SeniorReviewResult,
    TestCase,
)

logger = logging.getLogger(__name__)

# Seeded AgentConfig.agent_id for the senior reviewer.
SENIOR_REVIEWER_AGENT_ID = "senior_api_test_reviewer"

_OUTPUT_CONTRACT = (
    "Return ONLY a JSON object with these keys: "
    '"verdict" (one of approve|revise|reject), '
    '"evidence" (str — concise justification), '
    '"gaps" (array of str — missing edge cases / scenarios), '
    '"unsafe_assumptions" (array of str — invented behaviour not in the spec), '
    '"feedback" (str — targeted, actionable guidance for the next planning '
    "iteration). Emit no prose, no markdown fences, and never echo secret "
    "credential values."
)


class SeniorApiTestReviewerCrew(BaseCrew):
    """Run one senior reviewer agent over a consolidated test plan."""

    stage = "testcase"
    agent_ids: list[str] = [SENIOR_REVIEWER_AGENT_ID]

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

    # ── Required by BaseCrew (not the primary entry point) ────────────────────

    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Adapter so the crew satisfies the BaseCrew contract.

        ``input_data`` carries ``test_cases`` + ``coverage``. The review loop
        normally calls :meth:`review` directly with typed objects.
        """
        cases = [TestCase.model_validate(c) for c in input_data.get("test_cases", [])]
        coverage = CoverageReport.model_validate(input_data.get("coverage") or {})
        return self.review(cases, coverage).model_dump()

    # ── Primary entry point used by the review loop ───────────────────────────

    def review(
        self, cases: list[TestCase], coverage: CoverageReport
    ) -> SeniorReviewResult:
        """Produce a senior review for *cases* given their *coverage*.

        Falls back to a deterministic coverage-only verdict on mock mode,
        reviewer failure, or unparseable output.
        """
        if self._is_mock_mode():
            return self._fallback(coverage, reason="mock mode")

        try:
            raw = self._run_async_from_thread(
                self._invoke_reviewer(cases, coverage), timeout=180.0
            )
            return self._map_review(raw)
        except Exception as exc:  # noqa: BLE001 — documented fallback, no retry
            logger.warning(
                "[SeniorReviewer][%s] review failed: %s", self._run_id, exc
            )
            self._emit_log(
                f"Senior reviewer unavailable ({exc}); using deterministic "
                "coverage-only verdict.",
                level="warning",
            )
            return self._fallback(coverage, reason=str(exc))

    # ── LLM invocation ────────────────────────────────────────────────────────

    async def _invoke_reviewer(
        self, cases: list[TestCase], coverage: CoverageReport
    ) -> Any:
        from crewai import Crew, Process, Task  # type: ignore[import-untyped]

        from app.core.agent_factory import AgentFactory

        factory = AgentFactory(run_profile_id=self._run_profile_id)
        agent = await factory.build(SENIOR_REVIEWER_AGENT_ID)
        description, expected_output = self._build_prompt(cases, coverage)
        task = Task(description=description, expected_output=expected_output, agent=agent)
        crew = Crew(
            agents=[agent], tasks=[task], process=Process.sequential, verbose=False
        )
        import asyncio

        return await asyncio.to_thread(crew.kickoff)

    @staticmethod
    def _build_prompt(
        cases: list[TestCase], coverage: CoverageReport
    ) -> tuple[str, str]:
        """Render a secret-free reviewer prompt summarising the plan."""
        plan_digest = [
            {
                "id": c.id,
                "title": c.title,
                "method": (c.http_method or "").upper(),
                "endpoint": c.api_endpoint,
                "expected_status": c.expected_status_code,
                "category": getattr(c.category, "value", str(c.category)),
                "obligation_ids": c.obligation_ids,
                "is_assumption": c.is_assumption,
            }
            for c in cases
        ]
        coverage_digest = {
            "coverage_percent": coverage.coverage_percent,
            "covered_required": coverage.covered_required,
            "total_required": coverage.total_required,
            "uncovered": [
                {"id": g.obligation_id, "kind": g.kind, "description": g.description}
                for g in coverage.gaps
            ],
        }
        description = "\n".join(
            [
                "You are a SENIOR API test reviewer. Critically assess the "
                "consolidated test plan below for correctness, internal "
                "contradictions, unsafe assumptions, executability, and missing "
                "edge cases. The numeric coverage is computed deterministically "
                "and is authoritative — do not restate or override it; focus on "
                "qualitative soundness.",
                "",
                "DETERMINISTIC COVERAGE (authoritative):",
                json.dumps(coverage_digest, ensure_ascii=False, default=str),
                "",
                "CONSOLIDATED TEST PLAN (anonymised):",
                json.dumps(plan_digest, ensure_ascii=False, default=str),
                "",
                "Verdict guidance: 'approve' = sound and executable; 'revise' = "
                "fixable gaps or weak cases; 'reject' = contradictory, unsafe, or "
                "non-executable. Provide targeted feedback the planners can act on.",
                "",
                _OUTPUT_CONTRACT,
            ]
        )
        expected_output = (
            'A JSON object {"verdict": "...", "evidence": "...", "gaps": [...], '
            '"unsafe_assumptions": [...], "feedback": "..."}. No prose, no markdown.'
        )
        return description, expected_output

    # ── Output mapping + fallback ─────────────────────────────────────────────

    def _map_review(self, raw: Any) -> SeniorReviewResult:
        """Map raw agent JSON → SeniorReviewResult, defaulting safely."""
        parsed = self._parse_json_output(raw)
        if not isinstance(parsed, dict) or "raw_output" in parsed:
            raise ValueError("senior reviewer returned non-JSON output")

        verdict_raw = str(parsed.get("verdict") or "").strip().lower()
        try:
            verdict = ReviewVerdict(verdict_raw)
        except ValueError:
            # Unknown verdict is treated as 'revise' (safe, non-terminal).
            verdict = ReviewVerdict.REVISE

        def _str_list(value: Any) -> list[str]:
            if not isinstance(value, list):
                return []
            return [str(v) for v in value if isinstance(v, (str, int, float))]

        return SeniorReviewResult(
            verdict=verdict,
            evidence=str(parsed.get("evidence") or ""),
            gaps=_str_list(parsed.get("gaps")),
            unsafe_assumptions=_str_list(parsed.get("unsafe_assumptions")),
            feedback=str(parsed.get("feedback") or ""),
            fallback=False,
        )

    @staticmethod
    def _fallback(coverage: CoverageReport, *, reason: str) -> SeniorReviewResult:
        """Deterministic coverage-only verdict when the LLM is unavailable.

        Never fabricates gaps: it mirrors the deterministic coverage gaps as
        feedback and approves only when nothing is uncovered.
        """
        approved = not coverage.gaps
        feedback = ""
        if coverage.gaps:
            feedback = "Cover the missing required obligations: " + ", ".join(
                g.obligation_id for g in coverage.gaps
            )
        return SeniorReviewResult(
            verdict=ReviewVerdict.APPROVE if approved else ReviewVerdict.REVISE,
            evidence=f"Deterministic fallback ({reason}).",
            gaps=[],
            unsafe_assumptions=[],
            feedback=feedback,
            fallback=True,
        )
