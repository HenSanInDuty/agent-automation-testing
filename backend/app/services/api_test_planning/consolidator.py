"""
services/api_test_planning/consolidator.py
────────────────────────────────────────────
Deterministic obligation extraction + candidate consolidation.

Responsibilities
================
* :func:`extract_obligations` — normalize a parsed spec into traceable
  :class:`SourceObligation` rows (responses, headers, auth, fields, rules).
* :func:`case_fingerprint` — a stable semantic fingerprint of a test case used
  to detect duplicates regardless of which agent proposed it.
* :func:`consolidate` — merge the deterministic baseline with agent proposals,
  drop semantic duplicates (baseline wins), renumber IDs, and surface
  provenance, assumptions, and the duplicate count.

Everything here is pure and deterministic — no LLM, no I/O.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Iterable

from app.schemas.pipeline_io import SourceObligation, TestCase
from app.tools.md_api_spec_validator import ParsedSpec

# Replace the substituted unknown-id path-param value back to a placeholder so
# a baseline 404 case and an agent 404 case fingerprint identically.
_RE_LONG_DIGITS = re.compile(r"\b\d{4,}\b")


def extract_obligations(parsed: ParsedSpec) -> list[SourceObligation]:
    """Build the normalized obligation matrix from *parsed*.

    Each obligation gets a stable ``OBL-NNN`` id assigned in a fixed traversal
    order so the ids are deterministic for a given spec:

        1. spec-level headers (shared, emitted ONCE — never per endpoint, so a
           shared header does not inflate the coverage denominator);
        2. then, per endpoint in document order: responses → auth → fields/rules.
    """
    obligations: list[SourceObligation] = []
    counter = 1

    def _add(
        kind: str, description: str, evidence: str = "", required: bool = True
    ) -> None:
        nonlocal counter
        obligations.append(
            SourceObligation(
                id=f"OBL-{counter:03d}",
                kind=kind,
                description=description,
                evidence=evidence,
                required=required,
            )
        )
        counter += 1

    # Spec-level headers are shared across every endpoint — emit once.
    for header in parsed.headers:
        _add(
            "header",
            f"Header `{header.name}` is "
            + ("required" if header.required else "accepted"),
            evidence=(header.value_schema or "")[:120],
            # An accepted (optional) header is not mandatory coverage — it must
            # not inflate or deflate the deterministic coverage score.
            required=bool(header.required),
        )

    for ep in parsed.endpoints:
        prefix = f"{(ep.endpoint.method or '').upper()} {ep.endpoint.path}".strip()
        for resp in ep.responses:
            _add(
                "response",
                f"{prefix} must return HTTP {resp.status_code}"
                + (f" — {resp.description}" if resp.description else ""),
                evidence=(resp.payload_preview or "")[:160],
            )

        if (ep.endpoint.auth or "").strip():
            _add("auth", f"{prefix} requests must satisfy auth: {ep.endpoint.auth.strip()}")

        for field in ep.request.body_fields:
            if field.required:
                _add("field", f"{prefix} body field `{field.name}` is required")
            if (field.rules or "").strip():
                _add(
                    "rule",
                    f"{prefix} body field `{field.name}` must satisfy: {field.rules.strip()}",
                )

    return obligations


def _normalize_path(path: str | None) -> str:
    """Collapse path-param values so equivalent cases fingerprint the same."""
    if not path:
        return ""
    return _RE_LONG_DIGITS.sub("{id}", path.strip())


def _body_signature(body: dict | None) -> str:
    """Order-independent signature of a request body's shape + values."""
    if not body:
        return ""
    try:
        return json.dumps(body, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return repr(sorted(body.keys()))


def case_fingerprint(case: TestCase) -> str:
    """Return a stable semantic fingerprint for *case*.

    Two cases that exercise the same endpoint+method with the same input
    mutation and the same expected outcome collapse to one fingerprint, even
    if their titles or originating agents differ.
    """
    method = (case.http_method or "").upper()
    endpoint = _normalize_path(case.api_endpoint)
    body_sig = _body_signature(case.request_body)
    status = case.expected_status_code if case.expected_status_code is not None else ""
    category = getattr(case.category, "value", str(case.category))

    canonical = f"{method}|{endpoint}|{category}|{status}|{body_sig}"
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()  # noqa: S324


def consolidate(
    baseline: list[TestCase],
    proposals: Iterable[list[TestCase]],
) -> tuple[list[TestCase], int, list[str]]:
    """Merge baseline + agent proposals, dropping semantic duplicates.

    Baseline cases are authoritative: a proposal that fingerprints onto an
    existing case is discarded (counted as a duplicate). Surviving cases are
    renumbered ``TC-001…`` in stable order (baseline first, then proposals in
    iteration order) while preserving each case's provenance fields.

    Args:
        baseline:  Deterministic rule-based cases (``source_role='baseline'``).
        proposals: Per-agent candidate lists (already typed as TestCase).

    Returns:
        ``(final_cases, duplicates_removed, assumptions)`` where *assumptions*
        lists the titles of surviving cases flagged ``is_assumption=True``.
    """
    seen: set[str] = set()
    final: list[TestCase] = []
    duplicates = 0

    def _take(case: TestCase) -> None:
        nonlocal duplicates
        fp = case_fingerprint(case)
        if fp in seen:
            duplicates += 1
            return
        seen.add(fp)
        final.append(case)

    for case in baseline:
        _take(case)
    for proposal in proposals:
        for case in proposal:
            _take(case)

    # Renumber ids deterministically while keeping all provenance metadata.
    assumptions: list[str] = []
    for idx, case in enumerate(final, start=1):
        case.id = f"TC-{idx:03d}"
        if case.is_assumption:
            assumptions.append(case.title)

    return final, duplicates, assumptions
