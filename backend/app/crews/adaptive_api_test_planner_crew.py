"""
crews/adaptive_api_test_planner_crew.py
─────────────────────────────────────────
Bounded multi-agent API test planner.

Pipeline within this single pure-Python node:

1. Deterministic rule-based **baseline** (:func:`generate_test_cases`).
2. **Complexity** decision → select 1-5 specialised planner roles.
3. Run the selected planner agents **concurrently** (capped at 5). A failing
   agent is isolated; its peers and the baseline survive.
4. One **critique/debate** round when two or more agents succeed.
5. Deterministic **consolidation**: merge baseline + proposals, drop semantic
   duplicates (baseline wins), keep provenance, obligations, and assumptions.

The baseline is always retained, so an LLM outage or mock mode still yields a
valid, executable test suite plus a visible warning.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from app.crews.base_crew import BaseCrew, ProgressCallback
from app.schemas.pipeline_io import (
    PlannerRole,
    TestCase,
    TestCaseOutput,
    TestCategory,
    TestLevel,
    TestType,
)
from app.crews.request_body_synthesizer_crew import RequestBodySynthesizerCrew
from app.crews.senior_api_test_reviewer_crew import SeniorApiTestReviewerCrew
from app.services.api_test_planning.complexity import compute_complexity
from app.services.api_test_planning.consolidator import (
    consolidate,
    extract_obligations,
)
from app.services.api_test_planning.planner_prompts import (
    ROLE_AGENT_IDS,
    build_planner_prompt,
)
from app.services.api_test_planning.review_loop import (
    resolve_review_config,
    run_review_loop,
)
from app.tools.api_test_case_generator import generate_test_cases
from app.tools.header_redaction import redact_headers
from app.tools.md_api_spec_validator import ParsedSpec

logger = logging.getLogger(__name__)

# Hard cap on concurrent LLM planner calls — defends cost/latency even if a
# future config tries to widen the band beyond five.
_MAX_CONCURRENT_PLANNERS = 5


def _coerce_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_category(value: Any) -> TestCategory:
    try:
        return TestCategory(str(value).lower())
    except ValueError:
        return TestCategory.POSITIVE


class AdaptiveApiTestPlannerCrew(BaseCrew):
    """Generate API test cases via a bounded baseline + planner debate."""

    stage = "testcase"
    agent_ids: list[str] = list(ROLE_AGENT_IDS.values())

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

    # ── Entry point ──────────────────────────────────────────────────────────

    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        self._emit_agent_started("adaptive_api_test_planner", "Adaptive Test Planner")

        parsed = self._coerce_spec(input_data)
        if parsed is None:
            self._emit_agent_completed(
                "adaptive_api_test_planner", output_preview="no parsed spec"
            )
            return {"test_cases": [], "total_test_cases": 0}

        document_content = str(input_data.get("document_content") or "")
        requirement_ids = [
            str(r.get("id"))
            for r in (input_data.get("requirements") or [])
            if isinstance(r, dict) and r.get("id")
        ]
        requirement_id = requirement_ids[0] if requirement_ids else "REQ-001"

        body_seeds = self._synthesize_bodies(parsed)
        baseline_output = generate_test_cases(
            parsed=parsed,
            document_content=document_content,
            requirement_ids=requirement_ids,
            body_seeds=body_seeds,
        )
        baseline_cases = baseline_output.test_cases
        obligations = extract_obligations(parsed)

        # Effective config = template node defaults (config_overrides) overlaid
        # by per-run overrides (validated run_params surfaced at input top-level).
        node_cfg = input_data.get("__node_config__") or {}

        def _cfg(key: str) -> Any:
            val = input_data.get(key)
            return val if val is not None else node_cfg.get(key)

        min_agents = _coerce_int(_cfg("min_planner_agents")) or 1
        max_agents = _coerce_int(_cfg("max_planner_agents")) or 5
        complexity = compute_complexity(
            parsed, min_agents=min_agents, max_agents=max_agents
        )
        self._emit_log(complexity.rationale, level="info")

        base_executable = bool(parsed.base_url)
        warnings: list[str] = []
        iteration_meta: list[int] = []  # duplicates removed, per iteration

        def _add_warning(msg: str) -> None:
            if msg not in warnings:
                warnings.append(msg)

        def plan_fn(feedback: Optional[str]) -> list[TestCase]:
            """Produce one consolidated plan, optionally guided by gap feedback."""
            proposals: list[list[TestCase]] = []
            if self._is_mock_mode():
                _add_warning("Mock mode — planner agents skipped; baseline cases only.")
            else:
                try:
                    proposals, agent_warnings = self._run_async_from_thread(
                        self._run_planners(
                            parsed, obligations, complexity, requirement_id,
                            base_executable, feedback=feedback,
                        ),
                        timeout=300.0,
                    )
                    for w in agent_warnings:
                        _add_warning(w)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "[AdaptivePlanner][%s] planner phase failed: %s",
                        self._run_id, exc,
                    )
                    _add_warning(f"Adaptive planners failed ({exc}); baseline retained.")

            cases, duplicates, _assumptions = consolidate(baseline_cases, proposals)
            iteration_meta.append(duplicates)
            return cases

        reviewer = SeniorApiTestReviewerCrew(
            run_id=self._run_id,
            run_profile_id=self._run_profile_id,
            progress_callback=self._progress_callback,
            mock_mode=self._mock_mode,
        )
        reviewer._event_loop = self._event_loop

        def review_fn(cases: list[TestCase], coverage: Any) -> Any:
            return reviewer.review(cases, coverage)

        def emit_fn(
            iteration: int, coverage: Any, verdict: Any, remaining: int
        ) -> None:
            self._emit(
                "planner.review_iteration",
                {
                    "iteration": iteration,
                    "coverage_percent": coverage.coverage_percent,
                    "threshold": review_config.coverage_threshold_percent,
                    "verdict": verdict.value,
                    "attempts_remaining": remaining,
                },
            )

        review_config = resolve_review_config(
            {
                key: _cfg(key)
                for key in (
                    "coverage_threshold_percent",
                    "max_review_iterations",
                    "continue_on_exhaustion",
                )
            }
        )
        final_cases, review_gate = run_review_loop(
            obligations=obligations,
            plan_fn=plan_fn,
            review_fn=review_fn,
            config=review_config,
            emit=emit_fn,
        )

        # Defence-in-depth: mask any literal secret value on a sensitive header
        # before the plan is persisted, emitted, or exported. Placeholder values
        # (e.g. ${TOKEN}) are preserved so executable cases still render.
        for case in final_cases:
            if isinstance(case.request_headers, dict):
                case.request_headers = redact_headers(case.request_headers)

        # Selected-iteration metadata (assumptions derive from the chosen plan).
        sel = review_gate.selected_iteration
        duplicates = iteration_meta[sel] if sel < len(iteration_meta) else 0
        assumptions = [c.title for c in final_cases if c.is_assumption]
        # Surface the gate outcome in the run-level warnings for DB/UI/exports.
        warnings.extend(review_gate.warnings)

        output = TestCaseOutput(
            test_cases=final_cases,
            total_test_cases=len(final_cases),
            coverage_summary=baseline_output.coverage_summary,
            automation_readiness=baseline_output.automation_readiness,
            design_notes=baseline_output.design_notes
            + [
                f"Adaptive planner: {complexity.agent_count} agent(s) "
                f"({', '.join(r.value for r in complexity.selected_roles)}); "
                f"{duplicates} duplicate(s) removed; "
                f"coverage {review_gate.final_coverage_percent}% "
                f"(threshold {review_gate.coverage_threshold_percent}%), "
                f"verdict={review_gate.final_verdict.value}"
                + (", gate exhausted" if review_gate.coverage_gate_exhausted else "")
                + "."
            ],
            risks=baseline_output.risks,
            recommendations=baseline_output.recommendations,
            complexity=complexity,
            obligations=obligations,
            planner_warnings=warnings,
            assumptions=assumptions,
            duplicates_removed=duplicates,
            review_gate=review_gate,
        )

        for warning in warnings:
            self._emit_log(warning, level="warning")
        self._emit_agent_completed(
            "adaptive_api_test_planner",
            output_preview=(
                f"{len(final_cases)} case(s) · {complexity.agent_count} planner(s) · "
                f"coverage {review_gate.final_coverage_percent}%"
            ),
        )
        return output.model_dump()

    # ── Request body synthesis ────────────────────────────────────────────────

    def _synthesize_bodies(self, parsed: ParsedSpec) -> dict[str, dict[str, Any]]:
        """Best-effort LLM refinement of happy-path bodies.

        Returns ``{}`` on mock mode or any failure — the deterministic resolver
        in :func:`generate_test_cases` then supplies valid (if generic) bodies,
        so the baseline is never blocked.
        """
        if self._is_mock_mode():
            return {}
        synth = RequestBodySynthesizerCrew(
            run_id=self._run_id,
            run_profile_id=self._run_profile_id,
            progress_callback=self._progress_callback,
            mock_mode=self._mock_mode,
        )
        synth._event_loop = self._event_loop
        try:
            return synth.synthesize(parsed)
        except Exception as exc:  # noqa: BLE001 — documented fallback, no retry
            logger.warning(
                "[AdaptivePlanner][%s] body synthesis failed: %s",
                self._run_id, exc,
            )
            return {}

    # ── Planner orchestration ────────────────────────────────────────────────

    async def _run_planners(
        self,
        parsed: ParsedSpec,
        obligations: list,
        complexity: Any,
        requirement_id: str,
        base_executable: bool,
        feedback: Optional[str] = None,
    ) -> tuple[list[list[TestCase]], list[str]]:
        """Run the selected planners concurrently, then one critique round.

        *feedback* (when set) carries targeted coverage/review gaps from the
        previous gate iteration and is injected into every planner prompt so
        the next plan focuses on closing those gaps.
        """
        from app.core.agent_factory import AgentFactory

        factory = AgentFactory(run_profile_id=self._run_profile_id)
        roles = complexity.selected_roles[:_MAX_CONCURRENT_PLANNERS]
        warnings: list[str] = []

        results = await asyncio.gather(
            *[
                self._invoke_planner(
                    factory, role, parsed, obligations, requirement_id,
                    base_executable, peer_summary=None, feedback=feedback,
                )
                for role in roles
            ],
            return_exceptions=True,
        )

        proposals: dict[PlannerRole, list[TestCase]] = {}
        for role, result in zip(roles, results):
            if isinstance(result, Exception) or not result:
                warnings.append(
                    f"Planner '{role.value}' produced no usable cases; skipped."
                )
                continue
            proposals[role] = result

        # ── One critique/debate round when two or more agents succeeded ──────
        if len(proposals) >= 2:
            self._emit("planner.debate", {"agents": [r.value for r in proposals]})
            peer_summary = self._anonymised_summary(proposals)
            refined = await asyncio.gather(
                *[
                    self._invoke_planner(
                        factory, role, parsed, obligations, requirement_id,
                        base_executable, peer_summary=peer_summary,
                        feedback=feedback,
                    )
                    for role in proposals
                ],
                return_exceptions=True,
            )
            for role, result in zip(list(proposals), refined):
                if not isinstance(result, Exception) and result:
                    proposals[role] = result  # refined supersedes round-1

        return list(proposals.values()), warnings

    async def _invoke_planner(
        self,
        factory: Any,
        role: PlannerRole,
        parsed: ParsedSpec,
        obligations: list,
        requirement_id: str,
        base_executable: bool,
        *,
        peer_summary: Optional[str],
        feedback: Optional[str] = None,
    ) -> list[TestCase]:
        """Build + run a single planner agent and map its JSON to TestCases."""
        from crewai import Crew, Process, Task  # type: ignore[import-untyped]

        agent = await factory.build(ROLE_AGENT_IDS[role])
        description, expected_output = build_planner_prompt(
            role, parsed, obligations, peer_summary=peer_summary, feedback=feedback
        )
        task = Task(description=description, expected_output=expected_output, agent=agent)
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        raw = await asyncio.to_thread(crew.kickoff)
        return self._map_proposal(raw, role, requirement_id, base_executable)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _coerce_spec(self, input_data: dict[str, Any]) -> Optional[ParsedSpec]:
        parsed_dict = input_data.get("md_spec_parsed") or {}
        if not parsed_dict:
            self._emit_log(
                "md_spec_parsed missing from input — emitting empty test suite.",
                level="warning",
            )
            return None
        try:
            return ParsedSpec.model_validate(parsed_dict)
        except Exception as exc:  # noqa: BLE001
            self._emit_log(
                f"Could not coerce md_spec_parsed into ParsedSpec ({exc}); "
                "emitting empty test suite.",
                level="warning",
            )
            return None

    @staticmethod
    def _anonymised_summary(proposals: dict[PlannerRole, list[TestCase]]) -> str:
        """One-line-per-case digest with no role attribution or secrets."""
        lines: list[str] = []
        for cases in proposals.values():
            for case in cases:
                lines.append(
                    f"- {(case.http_method or '').upper()} {case.api_endpoint} "
                    f"→ {case.expected_status_code} ({case.category.value})"
                )
        return "\n".join(lines)

    def _map_proposal(
        self,
        raw: Any,
        role: PlannerRole,
        requirement_id: str,
        base_executable: bool,
    ) -> list[TestCase]:
        """Map raw agent JSON → list[TestCase]; quarantine invalid output."""
        parsed = self._parse_json_output(raw)
        items = parsed.get("test_cases") if isinstance(parsed, dict) else parsed
        if not isinstance(items, list):
            raise ValueError(f"planner '{role.value}' output missing test_cases array")

        cases: list[TestCase] = []
        quarantined = 0
        for idx, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                quarantined += 1
                continue
            raw_headers = item.get("request_headers")
            # Coerce header values to str so a valid case with an int-valued
            # header (e.g. {"X-Count": 5}) is not needlessly quarantined.
            headers = (
                {str(k): str(v) for k, v in raw_headers.items()}
                if isinstance(raw_headers, dict) else None
            )
            try:
                cases.append(
                    TestCase(
                        id=f"{role.value}-{idx:03d}",
                        requirement_id=requirement_id,
                        title=str(item.get("title") or f"{role.value} case {idx}"),
                        description=str(item.get("description") or ""),
                        test_type=TestType.API,
                        category=_coerce_category(item.get("category")),
                        priority=str(item.get("priority") or "medium"),
                        tags=[role.value, "adaptive-planner"],
                        api_endpoint=item.get("api_endpoint"),
                        http_method=(str(item.get("http_method") or "").upper() or None),
                        request_headers=headers,
                        request_body=item.get("request_body")
                        if isinstance(item.get("request_body"), dict) else None,
                        expected_status_code=_coerce_int(item.get("expected_status_code")),
                        test_level=TestLevel.INTEGRATION,
                        executable=base_executable,
                        classification_confidence=0.0,
                        skip_reason=None if base_executable else "No Base URL declared in MD spec.",
                        obligation_ids=[
                            str(x) for x in (item.get("obligation_ids") or [])
                            if isinstance(x, (str, int))
                        ],
                        source_role=role.value,
                        is_assumption=bool(item.get("is_assumption", True)),
                    )
                )
            except Exception:  # noqa: BLE001 — quarantine a single malformed case
                quarantined += 1
                continue
        if quarantined:
            self._emit_log(
                f"Planner '{role.value}': quarantined {quarantined} malformed "
                f"case(s); kept {len(cases)}.",
                level="warning",
            )
        return cases
