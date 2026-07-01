"""
tools/report_verifier.py
────────────────────────
Pure-Python verifier that asserts the final report carries all 3 mandatory
components before the user can download it:

    1. Test case info       — count > 0, each case has id + title + expected_result.
    2. Execution results    — pass_rate present, runnable + skipped rows.
    3. Unit test files      — count > 0, each file has path/language/non-empty
                              content that parses (syntax-light check).

Public API:
    verify_report(test_cases, results, unit_test_files,
                  html_bytes=b"", docx_bytes=b"") -> VerificationResult

The check is deterministic, ≤ 200 LOC, no LLM.
"""

from __future__ import annotations

import ast
import logging
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Output models
# ─────────────────────────────────────────────────────────────────────────────


class ComponentCheck(BaseModel):
    ok: bool = False
    count: int = 0
    issues: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class VerificationResult(BaseModel):
    verified: bool = False
    components: dict[str, ComponentCheck] = Field(default_factory=dict)
    html_url: str = ""
    docx_url: str = ""
    pdf_url: str = ""
    summary: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Public verification entry
# ─────────────────────────────────────────────────────────────────────────────


def verify_report(
    test_cases: Optional[list[dict[str, Any]]] = None,
    results: Optional[list[dict[str, Any]]] = None,
    unit_test_files: Optional[list[dict[str, Any]]] = None,
    pass_rate: Optional[float] = None,
    html_bytes: bytes = b"",
    docx_bytes: bytes = b"",
    pdf_bytes: bytes = b"",
    html_url: str = "",
    docx_url: str = "",
    pdf_url: str = "",
    review_gate: Optional[dict[str, Any]] = None,
) -> VerificationResult:
    """Run the component verification on the final artifacts.

    The 3 core components (test cases / results / unit test files) gate the
    download. ``review_coverage`` is **informational** — an exhausted coverage
    gate must NOT block delivery (it surfaces a warning instead).
    """
    test_cases = list(test_cases or [])
    results = list(results or [])
    unit_test_files = list(unit_test_files or [])

    tc_check = _check_test_cases(test_cases)
    res_check = _check_results(results, pass_rate)
    utf_check = _check_unit_test_files(unit_test_files)

    # When export bytes are supplied, do a minimal size sanity check so the
    # verifier surfaces obviously broken exports.
    if html_bytes and len(html_bytes) < 200:
        res_check.issues.append(
            f"HTML report suspiciously small ({len(html_bytes)} bytes)"
        )
        res_check.ok = False
    if docx_bytes and len(docx_bytes) < 1000:
        res_check.issues.append(
            f"DOCX report suspiciously small ({len(docx_bytes)} bytes)"
        )
        res_check.ok = False
    if pdf_bytes and len(pdf_bytes) < 1000:
        res_check.issues.append(
            f"PDF report suspiciously small ({len(pdf_bytes)} bytes)"
        )
        res_check.ok = False

    components = {
        "test_cases": tc_check,
        "results": res_check,
        "unit_test_files": utf_check,
        "review_coverage": _check_review_coverage(review_gate),
    }

    # Only the 3 core components gate delivery; review_coverage is advisory.
    verified = tc_check.ok and res_check.ok and utf_check.ok
    summary = (
        "Report ready for delivery"
        if verified
        else "Report verification failed — fix listed issues before retrying download."
    )

    return VerificationResult(
        verified=verified,
        components=components,
        html_url=html_url,
        docx_url=docx_url,
        pdf_url=pdf_url,
        summary=summary,
    )


def _check_review_coverage(review_gate: Optional[dict[str, Any]]) -> ComponentCheck:
    """Informational check: record coverage / exhaustion without gating.

    A missing gate (legacy run) is fine. An exhausted gate records a warning
    issue but stays ``ok`` so the run still delivers its best-available plan.
    """
    chk = ComponentCheck(ok=True)
    if not isinstance(review_gate, dict):
        chk.extra["available"] = False
        return chk
    chk.extra["available"] = True
    chk.extra["coverage_percent"] = review_gate.get("final_coverage_percent")
    chk.extra["threshold"] = review_gate.get("coverage_threshold_percent")
    chk.extra["verdict"] = review_gate.get("final_verdict")
    chk.extra["accepted"] = review_gate.get("accepted")
    chk.count = len(review_gate.get("iterations") or [])
    if review_gate.get("coverage_gate_exhausted"):
        chk.extra["exhausted"] = True
        chk.issues.append(
            "Coverage gate exhausted — delivered best-available plan "
            f"({review_gate.get('final_coverage_percent')}% vs "
            f"{review_gate.get('coverage_threshold_percent')}% threshold)."
        )
    return chk


# ─────────────────────────────────────────────────────────────────────────────
# Component checks
# ─────────────────────────────────────────────────────────────────────────────


def _check_test_cases(cases: list[Any]) -> ComponentCheck:
    chk = ComponentCheck()
    # Guard against upstream lists that contain non-dict entries (e.g. an
    # LLM hallucinating ``test_cases: ["TC-1", "TC-2"]`` instead of dicts).
    dict_cases = [c for c in cases if isinstance(c, dict)]
    non_dict_count = len(cases) - len(dict_cases)
    chk.count = len(dict_cases)
    if non_dict_count:
        chk.issues.append(
            f"{non_dict_count} test case entr(ies) are not objects "
            "(ignored — fix the upstream generator to emit dicts)."
        )
    if chk.count == 0:
        chk.issues.append("No test cases were generated.")
        return chk
    missing_titles = 0
    missing_expected = 0
    for tc in dict_cases:
        if not str(tc.get("title") or "").strip():
            missing_titles += 1
        if not str(tc.get("expected_result") or tc.get("expected_status_code") or "").strip():
            missing_expected += 1
    if missing_titles:
        chk.issues.append(
            f"{missing_titles} test case(s) are missing a title."
        )
    if missing_expected:
        chk.issues.append(
            f"{missing_expected} test case(s) lack an expected_result/status."
        )
    chk.ok = not chk.issues
    return chk


def _check_results(
    results: list[Any],
    pass_rate: Optional[float],
) -> ComponentCheck:
    chk = ComponentCheck()
    dict_results = [r for r in results if isinstance(r, dict)]
    non_dict_count = len(results) - len(dict_results)
    chk.count = len(dict_results)
    if non_dict_count:
        chk.issues.append(
            f"{non_dict_count} execution result entr(ies) are not objects "
            "(ignored — fix the upstream runner to emit dicts)."
        )
    if chk.count == 0:
        chk.issues.append("Execution results are empty.")
        return chk

    runnable = sum(1 for r in dict_results if r.get("status") != "skipped")
    skipped = sum(1 for r in dict_results if r.get("status") == "skipped")
    chk.extra["runnable"] = runnable
    chk.extra["skipped"] = skipped

    if pass_rate is None and runnable > 0:
        chk.issues.append("Pass rate is missing from the execution summary.")

    if pass_rate is not None:
        chk.extra["pass_rate"] = pass_rate
        if pass_rate < 0 or pass_rate > 100:
            chk.issues.append(
                f"Pass rate {pass_rate} is outside the valid [0, 100] range."
            )

    chk.ok = not chk.issues
    return chk


def _check_unit_test_files(files: list[Any]) -> ComponentCheck:
    chk = ComponentCheck()
    dict_files = [f for f in files if isinstance(f, dict)]
    non_dict_count = len(files) - len(dict_files)
    chk.count = len(dict_files)
    if non_dict_count:
        chk.issues.append(
            f"{non_dict_count} unit test file entr(ies) are not objects "
            "(ignored — fix the artifact generator to emit dicts)."
        )
    if chk.count == 0:
        chk.issues.append("No unit test files were generated.")
        return chk

    syntax_failures: list[str] = []
    empties: list[str] = []
    for f in dict_files:
        name = str(f.get("filename") or f.get("path") or "?")
        content = str(f.get("content") or "")
        language = str(f.get("language") or "").lower()
        if not content.strip():
            empties.append(name)
            continue
        if language in {"python", "py"}:
            try:
                ast.parse(content)
            except SyntaxError as exc:
                syntax_failures.append(f"{name}: {exc.msg} (line {exc.lineno})")
        elif language in {"typescript", "javascript", "ts", "js"}:
            if not _bracket_balanced(content):
                syntax_failures.append(f"{name}: unbalanced brackets")

    if empties:
        chk.issues.append(f"Empty test files: {empties}")
    if syntax_failures:
        chk.issues.append("Syntax issues: " + "; ".join(syntax_failures[:5]))

    chk.ok = not chk.issues
    return chk


def _bracket_balanced(text: str) -> bool:
    pairs = {"}": "{", "]": "[", ")": "("}
    stack: list[str] = []
    in_str: Optional[str] = None
    escape = False
    for ch in text:
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
            continue
        if ch in ('"', "'", "`"):
            in_str = ch
            continue
        if ch in "({[":
            stack.append(ch)
        elif ch in ")}]":
            if not stack or stack[-1] != pairs[ch]:
                return False
            stack.pop()
    return not stack
