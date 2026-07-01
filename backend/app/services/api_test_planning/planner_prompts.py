"""
services/api_test_planning/planner_prompts.py
──────────────────────────────────────────────
Role definitions and prompt construction for the adaptive planner agents.

Each :class:`~app.schemas.pipeline_io.PlannerRole` maps to a seeded agent_id
and a focus brief. :func:`build_planner_prompt` renders a strict-JSON task
prompt that anonymises peer proposals during the critique round and forbids
echoing secret credential values.
"""

from __future__ import annotations

import json
from typing import Optional

from app.schemas.pipeline_io import PlannerRole, SourceObligation
from app.tools.md_api_spec_validator import ParsedSpec

# PlannerRole → seeded AgentConfig.agent_id.
ROLE_AGENT_IDS: dict[PlannerRole, str] = {
    PlannerRole.POSITIVE: "adaptive_planner_positive",
    PlannerRole.NEGATIVE_SCHEMA: "adaptive_planner_negative_schema",
    PlannerRole.AUTH_SECURITY: "adaptive_planner_auth_security",
    PlannerRole.BOUNDARY_DATA: "adaptive_planner_boundary_data",
    PlannerRole.RESILIENCE_IDEMPOTENCY: "adaptive_planner_resilience",
}

# PlannerRole → one-line focus brief injected into the task prompt.
ROLE_FOCUS: dict[PlannerRole, str] = {
    PlannerRole.POSITIVE: (
        "valid happy-path requests covering every declared 2xx response, "
        "including correct content negotiation and fully-populated bodies"
    ),
    PlannerRole.NEGATIVE_SCHEMA: (
        "schema/validation failures — missing required fields, wrong types, "
        "malformed payloads — that must be rejected with a 4xx status"
    ),
    PlannerRole.AUTH_SECURITY: (
        "authentication and authorization failures — missing/invalid tokens "
        "and missing required headers expecting 401/403; never include real "
        "secret values, only placeholders"
    ),
    PlannerRole.BOUNDARY_DATA: (
        "boundary-value and equivalence-partition cases — min/max lengths, "
        "empty/null, zero, and oversized inputs at the edges of each rule"
    ),
    PlannerRole.RESILIENCE_IDEMPOTENCY: (
        "resilience and idempotency — repeated/duplicate requests, idempotent "
        "PUT/DELETE behaviour, and unknown-id lookups expecting 404"
    ),
}

_OUTPUT_CONTRACT = (
    "Return ONLY a JSON object of the form "
    '{"test_cases": [ ... ]}. Each test case object must use these keys: '
    '"title" (str), "description" (str), "category" '
    '(positive|negative|edge_case|boundary), "priority" (high|medium|low), '
    '"api_endpoint" (str), "http_method" (str), "request_headers" (object|null), '
    '"request_body" (object|null), "expected_status_code" (int), '
    '"obligation_ids" (array of obligation ids this case satisfies), '
    '"is_assumption" (bool — true when the behaviour is not explicitly stated '
    "in the spec). Emit no prose, no markdown fences, no secret credential "
    "values — use placeholders like ${TOKEN} for any secret."
)


def _spec_summary(parsed: ParsedSpec) -> str:
    """Compact, secret-free description of every endpoint under test."""
    endpoints = [
        {
            "method": (ep.endpoint.method or "GET").upper(),
            "path": ep.endpoint.path,
            "auth": ep.endpoint.auth or "",
            "body_fields": [
                {
                    "name": f.name,
                    "type": f.type or "any",
                    "required": f.required,
                    "rules": (f.rules or "")[:120],
                }
                for f in ep.request.body_fields
            ],
            "responses": [
                {"status": r.status_code, "description": r.description[:120]}
                for r in ep.responses
            ],
        }
        for ep in parsed.endpoints
    ]
    summary = {
        "base_url": parsed.base_url or "<unset>",
        # Header NAMES only — never emit declared header values into a prompt.
        "headers": [h.name for h in parsed.headers],
        "endpoints": endpoints,
    }
    return json.dumps(summary, ensure_ascii=False, default=str)


def build_planner_prompt(
    role: PlannerRole,
    parsed: ParsedSpec,
    obligations: list[SourceObligation],
    *,
    peer_summary: Optional[str] = None,
    feedback: Optional[str] = None,
) -> tuple[str, str]:
    """Render ``(description, expected_output)`` for a planner agent task.

    Args:
        role:         The planner concern this agent owns.
        parsed:       The validated spec under test.
        obligations:  Normalized obligations the cases should map back to.
        peer_summary: Anonymised digest of other agents' proposals. When set,
                      the prompt becomes a one-round critique/refinement pass.
        feedback:     Targeted coverage/review feedback from the previous gate
                      iteration. When set, the planner must prioritise closing
                      these specific gaps.
    """
    obligation_lines = "\n".join(
        f"- {o.id} [{o.kind}]: {o.description}" for o in obligations
    ) or "- (no explicit obligations parsed)"

    parts = [
        f"You are the {role.value.replace('_', ' ')} API test planner. "
        f"Focus exclusively on {ROLE_FOCUS[role]}.",
        "",
        "ENDPOINTS UNDER TEST (JSON):",
        _spec_summary(parsed),
        "",
        "SOURCE OBLIGATIONS (map each case back via obligation_ids):",
        obligation_lines,
    ]

    if peer_summary:
        parts += [
            "",
            "PEER PROPOSALS (anonymised) — critique round. Do NOT duplicate "
            "cases already covered below; add only the cases your role uniquely "
            "contributes or that the peers missed:",
            peer_summary,
        ]

    if feedback:
        parts += [
            "",
            "REVIEW FEEDBACK — the previous plan failed the coverage gate. "
            "Prioritise cases that close these specific gaps, within your role:",
            feedback,
        ]

    parts += ["", _OUTPUT_CONTRACT]
    description = "\n".join(parts)
    expected_output = (
        'A JSON object {"test_cases": [...]} of API test cases focused on '
        f"{role.value} concerns. No prose, no markdown."
    )
    return description, expected_output
