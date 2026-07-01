"""
services/api_test_planning/coverage.py
────────────────────────────────────────
Deterministic obligation-to-test coverage.

Coverage is computed purely from data — the normalized obligation inventory and
the ``obligation_ids`` each test case cites — never from an LLM self-score. The
same plan + obligation list always yields the same :class:`CoverageReport`, so
the gate decision is reproducible from what is persisted in MongoDB.

Coverage unit / formula
=======================
    coverage_percent = covered_required / total_required * 100

where *required* obligations are those flagged ``required=True`` (an optional /
"accepted" header is excluded so it never inflates or deflates the score). When
there are no required obligations, coverage is vacuously 100%.

Mappings cited by a case that do not exist in the inventory are reported under
``unknown_obligation_ids`` for diagnosis but never count as coverage.
"""

from __future__ import annotations

from typing import Iterable

from app.schemas.pipeline_io import (
    CoverageGap,
    CoverageReport,
    SourceObligation,
    TestCase,
)


def compute_coverage(
    cases: Iterable[TestCase],
    obligations: Iterable[SourceObligation],
) -> CoverageReport:
    """Compute deterministic obligation coverage for *cases*.

    Args:
        cases:       The consolidated test plan whose ``obligation_ids`` map
                     each case back to the obligations it satisfies.
        obligations: The normalized obligation inventory for the spec.

    Returns:
        A :class:`CoverageReport` with the required-obligation score, the list
        of uncovered required obligations (gaps), and any unknown ids cited.
    """
    obligation_list = list(obligations)
    obligation_index = {o.id: o for o in obligation_list}
    required = [o for o in obligation_list if o.required]
    required_ids = {o.id for o in required}

    cited: set[str] = set()
    unknown: set[str] = set()
    for case in cases:
        for oid in case.obligation_ids:
            if oid in obligation_index:
                cited.add(oid)
            else:
                unknown.add(oid)

    covered_required = required_ids & cited
    gaps = [
        CoverageGap(
            obligation_id=o.id,
            kind=o.kind,
            description=o.description,
        )
        for o in required
        if o.id not in covered_required
    ]

    return CoverageReport(
        total_required=len(required),
        covered_required=len(covered_required),
        gaps=gaps,
        # Sorted for deterministic output regardless of case iteration order.
        unknown_obligation_ids=sorted(unknown),
    )


def gaps_as_feedback(report: CoverageReport) -> str:
    """Render uncovered required obligations as targeted planner feedback.

    Returns an empty string when there are no coverage gaps, so callers can
    treat falsiness as "no actionable coverage gap this iteration".
    """
    if not report.gaps:
        return ""
    lines = [
        f"- {gap.obligation_id} [{gap.kind}]: {gap.description}"
        for gap in report.gaps
    ]
    return (
        "Uncovered required obligations — add test cases that cite these "
        "obligation_ids:\n" + "\n".join(lines)
    )
