"""
services/api_test_planning/review_loop.py
───────────────────────────────────────────
Bounded senior-review coverage gate.

The adaptive planner node owns a single internal loop::

    baseline -> planners/debate -> consolidate -> deterministic coverage -> senior review
                  ^                                              |
                  +----------- targeted gap feedback ------------+

The gate **passes** only when deterministic coverage meets the threshold *and*
the senior verdict is not ``reject``. On every failing iteration, concrete
coverage gaps + reviewer feedback are fed back into planning, up to
``max_review_iterations`` attempts after the initial plan.

The loop is bounded and acyclic by construction — it lives inside one DAG node
and never relies on node retry. On exhaustion it selects the highest-scoring
valid iteration deterministically, flags ``coverage_gate_exhausted``, and
returns the best plan so the run can continue (per config).

Everything here is pure orchestration over injected callables, so it is fully
unit-testable without an LLM or a database.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional

from app.schemas.pipeline_io import (
    CoverageReport,
    ReviewGateSummary,
    ReviewIteration,
    ReviewVerdict,
    SeniorReviewResult,
    SourceObligation,
    TestCase,
)
from app.services.api_test_planning.coverage import compute_coverage, gaps_as_feedback

logger = logging.getLogger(__name__)

# Verdict → rank for deterministic best-iteration selection (higher is better).
_VERDICT_RANK: dict[ReviewVerdict, int] = {
    ReviewVerdict.APPROVE: 2,
    ReviewVerdict.REVISE: 1,
    ReviewVerdict.REJECT: 0,
}


@dataclass(frozen=True)
class ReviewConfig:
    """Resolved, validated review-gate configuration for one run."""

    coverage_threshold_percent: float = 90.0
    max_review_iterations: int = 3
    continue_on_exhaustion: bool = True


def resolve_review_config(raw: Optional[dict]) -> ReviewConfig:
    """Validate + clamp review config from template defaults / run overrides.

    Bounds (from the plan's configuration contract):
      * ``coverage_threshold_percent`` 0-100
      * ``max_review_iterations`` 0-5
      * ``continue_on_exhaustion`` bool
    Invalid / missing values fall back to the documented defaults.
    """
    raw = raw or {}

    def _num(key: str, default: float, lo: float, hi: float) -> float:
        try:
            return max(lo, min(hi, float(raw[key])))
        except (KeyError, TypeError, ValueError):
            return default

    threshold = _num("coverage_threshold_percent", 90.0, 0.0, 100.0)
    iterations = int(_num("max_review_iterations", 3.0, 0.0, 5.0))

    continue_raw = raw.get("continue_on_exhaustion", True)
    continue_on_exhaustion = (
        bool(continue_raw) if isinstance(continue_raw, bool) else True
    )

    return ReviewConfig(
        coverage_threshold_percent=threshold,
        max_review_iterations=iterations,
        continue_on_exhaustion=continue_on_exhaustion,
    )


# A planner callable: given optional targeted feedback, produce a consolidated
# plan. Feedback is None on the first iteration.
PlanFn = Callable[[Optional[str]], "list[TestCase]"]
# A reviewer callable: given the plan + its deterministic coverage, return a
# qualitative senior review (or a deterministic fallback).
ReviewFn = Callable[["list[TestCase]", CoverageReport], SeniorReviewResult]
# Optional progress emitter: (iteration, coverage, verdict, attempts_remaining).
EmitFn = Callable[[int, CoverageReport, ReviewVerdict, int], None]


def _gate_passes(
    coverage: CoverageReport, review: SeniorReviewResult, threshold: float
) -> bool:
    """Gate passes only on sufficient coverage AND a non-reject verdict."""
    return (
        coverage.coverage_percent >= threshold
        and review.verdict != ReviewVerdict.REJECT
    )


def _build_feedback(coverage: CoverageReport, review: SeniorReviewResult) -> str:
    """Compose actionable feedback from coverage gaps + reviewer notes."""
    parts = [gaps_as_feedback(coverage)]
    if review.feedback.strip():
        parts.append(f"Senior reviewer feedback:\n{review.feedback.strip()}")
    if review.gaps:
        parts.append(
            "Reviewer-identified missing scenarios:\n"
            + "\n".join(f"- {g}" for g in review.gaps)
        )
    return "\n\n".join(p for p in parts if p)


def _select_best(iterations: list[ReviewIteration]) -> int:
    """Pick the best iteration deterministically when the gate never passed.

    Ranking key (descending): coverage_percent, then verdict rank
    (approve > revise > reject). Ties break toward the **earliest** iteration so
    selection is stable and reproducible.
    """
    best_idx = 0
    best_key = (-1.0, -1, 0)
    for it in iterations:
        key = (
            it.coverage.coverage_percent,
            _VERDICT_RANK.get(it.review.verdict, 0),
            -it.iteration,  # earlier wins on a tie
        )
        if key > best_key:
            best_key = key
            best_idx = it.iteration
    return best_idx


def run_review_loop(
    *,
    obligations: list[SourceObligation],
    plan_fn: PlanFn,
    review_fn: ReviewFn,
    config: ReviewConfig,
    emit: Optional[EmitFn] = None,
) -> tuple[list[TestCase], ReviewGateSummary]:
    """Drive the bounded plan→coverage→review loop and return the chosen plan.

    Returns ``(selected_plan, summary)``. The summary keeps the complete
    per-iteration audit; only the selected plan flows downstream.

    The loop short-circuits on the first passing gate, and otherwise stops early
    on deterministic no-progress (coverage did not improve and the same gaps
    persist) to avoid burning iterations that cannot help.
    """
    total_attempts = config.max_review_iterations + 1  # initial + n retries
    summary = ReviewGateSummary(
        coverage_threshold_percent=config.coverage_threshold_percent,
        max_review_iterations=config.max_review_iterations,
        continue_on_exhaustion=config.continue_on_exhaustion,
    )
    plans: dict[int, list[TestCase]] = {}
    feedback: Optional[str] = None
    prev_coverage: Optional[float] = None
    prev_gap_ids: Optional[frozenset[str]] = None

    for attempt in range(total_attempts):
        plan = plan_fn(feedback)
        coverage = compute_coverage(plan, obligations)
        review = review_fn(plan, coverage)
        accepted = _gate_passes(coverage, review, config.coverage_threshold_percent)

        plans[attempt] = plan
        summary.iterations.append(
            ReviewIteration(
                iteration=attempt,
                case_count=len(plan),
                coverage=coverage,
                review=review,
                accepted=accepted,
                feedback_applied=feedback or "",
            )
        )
        if emit is not None:
            emit(attempt, coverage, review.verdict, total_attempts - attempt - 1)

        if accepted:
            break

        # ── No-progress detection ────────────────────────────────────────────
        gap_ids = frozenset(g.obligation_id for g in coverage.gaps)
        if (
            prev_coverage is not None
            and coverage.coverage_percent <= prev_coverage
            and gap_ids == prev_gap_ids
        ):
            summary.warnings.append(
                f"No-progress detected at iteration {attempt}: coverage did not "
                "improve and the same obligations remain uncovered; stopping early."
            )
            break
        prev_coverage = coverage.coverage_percent
        prev_gap_ids = gap_ids

        # Only iterate when there is something actionable to fix.
        feedback = _build_feedback(coverage, review)
        if not feedback:
            summary.warnings.append(
                f"Iteration {attempt} fell short but produced no actionable "
                "feedback; stopping early."
            )
            break

    # ── Resolve the selected outcome ─────────────────────────────────────────
    passing = [it for it in summary.iterations if it.accepted]
    if passing:
        chosen = passing[0]  # first acceptance wins (we broke on it)
        summary.accepted = True
        summary.coverage_gate_exhausted = False
    else:
        best_idx = _select_best(summary.iterations)
        chosen = next(it for it in summary.iterations if it.iteration == best_idx)
        summary.accepted = False
        summary.coverage_gate_exhausted = True
        warn = (
            f"Coverage gate exhausted after {len(summary.iterations)} attempt(s); "
            f"best plan = iteration {chosen.iteration} "
            f"({chosen.coverage.coverage_percent}% vs "
            f"{config.coverage_threshold_percent}% threshold, "
            f"verdict={chosen.review.verdict.value})."
        )
        summary.warnings.append(warn)
        if not config.continue_on_exhaustion:
            summary.warnings.append(
                "continue_on_exhaustion=false — downstream execution proceeds "
                "with the best available plan but the gate did NOT pass."
            )
        logger.warning("[review_loop] %s", warn)

    summary.selected_iteration = chosen.iteration
    summary.final_coverage_percent = chosen.coverage.coverage_percent
    summary.final_verdict = chosen.review.verdict
    return plans[chosen.iteration], summary
