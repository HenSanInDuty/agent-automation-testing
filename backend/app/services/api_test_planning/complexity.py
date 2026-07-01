"""
services/api_test_planning/complexity.py
─────────────────────────────────────────
Deterministic complexity scoring + planner-role selection.

Given a :class:`~app.tools.md_api_spec_validator.ParsedSpec`, this module
counts stable structural signals, maps them to a bounded score, derives how
many specialised planners to run (1-5), and selects their roles in a fixed
priority order.

Determinism contract
=====================
The same parsed spec (and the same min/max bounds) always yields the same
score, the same agent count, and the same ordered role list. No randomness,
no I/O, no wall-clock dependency.
"""

from __future__ import annotations

from app.schemas.pipeline_io import ComplexityDecision, PlannerRole
from app.tools.md_api_spec_validator import ParsedSpec

# Methods that mutate server state — they justify resilience/idempotency cases.
_STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Per-signal weights. Tuned so a trivial GET (one 2xx, no body/auth) scores ~0
# and a rich state-changing POST (many validated fields, auth, several
# responses) comfortably crosses the top band.
_WEIGHTS: dict[str, int] = {
    "response_count": 1,
    "parameter_count": 1,
    "validation_rule_count": 2,
    "header_auth_count": 2,
    "state_changing": 3,
}

# Score → agent-count bands (inclusive lower bounds). Evaluated high → low.
_SCORE_BANDS: list[tuple[int, int]] = [
    (15, 5),
    (10, 4),
    (6, 3),
    (3, 2),
    (0, 1),
]

# Fixed selection priority. Slicing the first ``agent_count`` entries gives a
# deterministic, explainable role set for any count.
_ROLE_PRIORITY: list[PlannerRole] = [
    PlannerRole.POSITIVE,
    PlannerRole.NEGATIVE_SCHEMA,
    PlannerRole.AUTH_SECURITY,
    PlannerRole.BOUNDARY_DATA,
    PlannerRole.RESILIENCE_IDEMPOTENCY,
]


def _count_signals(parsed: ParsedSpec) -> dict[str, int]:
    """Count the stable structural signals used for scoring.

    Signals aggregate across ALL endpoints: response/parameter/rule counts sum
    over endpoints, ``state_changing`` is set if ANY endpoint mutates state, and
    ``header_auth_count`` is the spec-level header count plus the number of
    endpoints declaring auth. A richer multi-endpoint spec therefore scores
    higher and recruits more planners (still clamped to the configured bounds).
    """
    response_count = 0
    parameter_count = 0
    validation_rule_count = 0
    auth_count = 0
    state_changing = 0

    for ep in parsed.endpoints:
        method = (ep.endpoint.method or "GET").upper()
        body_fields = ep.request.body_fields
        response_count += len(ep.responses)
        parameter_count += len(body_fields)
        validation_rule_count += sum(
            1 for f in body_fields if f.required or (f.rules or "").strip()
        )
        if (ep.endpoint.auth or "").strip():
            auth_count += 1
        if method in _STATE_CHANGING_METHODS:
            state_changing = 1

    return {
        "response_count": response_count,
        "parameter_count": parameter_count,
        "validation_rule_count": validation_rule_count,
        "header_auth_count": len(parsed.headers) + auth_count,
        "state_changing": state_changing,
    }


def _score(signals: dict[str, int]) -> int:
    """Weighted sum of the counted signals."""
    return sum(_WEIGHTS[key] * value for key, value in signals.items())


def _agent_count(score: int, *, min_agents: int, max_agents: int) -> int:
    """Map a score to an agent count, clamped to the configured bounds."""
    raw = next(count for threshold, count in _SCORE_BANDS if score >= threshold)
    return max(min_agents, min(max_agents, raw))


def compute_complexity(
    parsed: ParsedSpec,
    *,
    min_agents: int = 1,
    max_agents: int = 5,
) -> ComplexityDecision:
    """Score *parsed* and select the planner roles to run.

    Args:
        parsed:     The validated MD API spec.
        min_agents: Lower bound on selected planners (config: min_planner_agents).
        max_agents: Upper bound on selected planners (config: max_planner_agents).

    Returns:
        A :class:`ComplexityDecision` with the score, raw signals, agent count,
        and the ordered list of selected roles.
    """
    # Defend the 1-5 invariant even if callers pass nonsense bounds.
    min_agents = max(1, min(5, min_agents))
    max_agents = max(min_agents, min(5, max_agents))

    signals = _count_signals(parsed)
    score = _score(signals)
    count = _agent_count(score, min_agents=min_agents, max_agents=max_agents)
    roles = _ROLE_PRIORITY[:count]

    rationale = (
        f"score={score} (responses={signals['response_count']}, "
        f"parameters={signals['parameter_count']}, "
        f"rules={signals['validation_rule_count']}, "
        f"headers/auth={signals['header_auth_count']}, "
        f"state_changing={signals['state_changing']}) → {count} planner(s) "
        f"[bounds {min_agents}-{max_agents}]."
    )

    return ComplexityDecision(
        score=score,
        signals=signals,
        agent_count=count,
        selected_roles=roles,
        rationale=rationale,
    )
