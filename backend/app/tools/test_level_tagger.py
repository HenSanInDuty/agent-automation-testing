"""
tools/test_level_tagger.py
──────────────────────────
Rule-based classifier that assigns ``test_level`` and ``executable`` to a
single :class:`TestCase`.

Phase 3 of the automation-testing-api plan. The classifier is deterministic
and cheap — it only consults the test case dict and an optional ``endpoint``
hint (from the MD spec verifier). LLM fallback is the caller's responsibility
when ``confidence < threshold``.

Public API:
    classify_test_level(test_case, endpoint_hint=None)
        → (TestLevel, executable: bool, confidence: float)
"""

from __future__ import annotations

from typing import Any, Optional

from app.schemas.pipeline_io import TestLevel

# Confidence threshold below which the caller should escalate to LLM.
_CONFIDENCE_LLM_FALLBACK_THRESHOLD = 0.7


def classify_test_level(
    test_case: dict[str, Any],
    endpoint_hint: Optional[dict[str, Any]] = None,
) -> tuple[TestLevel, bool, float]:
    """Return ``(level, executable, confidence)`` for *test_case*.

    Rules (first match wins):

    1. **e2e** — case carries ≥ 2 steps that reference distinct endpoints or
       requires multi-step authentication. ``executable=False`` (multi-step
       runner not yet supported).
    2. **integration** — case has ``api_endpoint`` (or inherits from
       ``endpoint_hint``) + ``http_method`` + ``expected_status_code``.
       ``executable=True``.
    3. **contract** — case has only schema validation / response-shape
       assertions, no concrete request. ``executable=False``.
    4. **unit** — field-level validation, no network. ``executable=True``
       (runnable inside generated unit-test files).
    5. **fallback** — :data:`TestLevel.UNIT`, executable=False, low conf.
    """
    if not isinstance(test_case, dict):
        return TestLevel.UNIT, False, 0.5

    steps = test_case.get("steps") or []
    api_endpoint = test_case.get("api_endpoint") or (
        endpoint_hint.get("path") if endpoint_hint else None
    )
    http_method = test_case.get("http_method") or (
        endpoint_hint.get("method") if endpoint_hint else None
    )
    expected_status = test_case.get("expected_status_code")
    test_type = str(test_case.get("test_type", "")).lower()
    category = str(test_case.get("category", "")).lower()
    tags = [str(t).lower() for t in (test_case.get("tags") or [])]
    title = str(test_case.get("title", "")).lower()
    description = str(test_case.get("description", "")).lower()

    # ── Rule 1: e2e (multi-step) ──────────────────────────────────────────
    distinct_endpoints = {
        str(step.get("action", "")).strip().lower()
        for step in steps
        if isinstance(step, dict) and "http" in str(step.get("action", "")).lower()
    }
    if len(steps) >= 3 and len(distinct_endpoints) >= 2:
        return TestLevel.E2E, False, 0.85
    if "e2e" in tags or "end-to-end" in tags or "end_to_end" in tags:
        return TestLevel.E2E, False, 0.9

    # ── Rule 2: integration ───────────────────────────────────────────────
    if api_endpoint and http_method and expected_status is not None:
        return TestLevel.INTEGRATION, True, 0.95

    if api_endpoint and http_method and (
        "integration" in tags or test_type in {"api", "integration"}
    ):
        # Has endpoint+method but no expected status — still runnable but
        # downstream runner will record actual code only.
        return TestLevel.INTEGRATION, True, 0.8

    # ── Rule 3: contract ──────────────────────────────────────────────────
    if "contract" in tags or any(
        kw in title or kw in description for kw in ("schema", "json schema", "contract")
    ):
        return TestLevel.CONTRACT, False, 0.8

    # ── Rule 4: unit ──────────────────────────────────────────────────────
    if (
        category in {"boundary", "edge_case", "negative", "positive"}
        and not api_endpoint
    ):
        return TestLevel.UNIT, True, 0.9

    if any(kw in title for kw in ("validate ", "validation", "boundary", "min ", "max ")):
        return TestLevel.UNIT, True, 0.85

    # ── Fallback ──────────────────────────────────────────────────────────
    return TestLevel.UNIT, False, 0.5


def needs_llm_fallback(confidence: float) -> bool:
    """Return True when *confidence* warrants an LLM-based re-classification."""
    return confidence < _CONFIDENCE_LLM_FALLBACK_THRESHOLD
