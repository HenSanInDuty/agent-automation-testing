"""
services/pdf_report_builder.py
────────────────────────────────
ReportLab PDF builder for the Auto-AT pipeline report.

Renders the SAME normalized context dict that drives the HTML/DOCX exports
(:meth:`ExportService._load_run_data`), so all three formats expose equivalent
core data. Sections, in order:

    1. Title + run metadata
    2. Executive summary + headline metrics
    3. Adaptive-planner decision (complexity)
    4. Coverage matrix (obligations + gaps) and senior-review history
    5. Exhaustion / planner warnings
    6. Test cases
    7. Execution results

Header values are already redacted upstream; this builder never prints
``request_headers``. Large tables are chunked so pagination stays bounded.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_DARK_BLUE = colors.HexColor("#1e3a5f")
_HEADER_BG = colors.HexColor("#1e3a5f")
_LIGHT_BG = colors.HexColor("#f8fafc")
_STATUS_COLORS = {
    "passed": colors.HexColor("#22c55e"),
    "failed": colors.HexColor("#ef4444"),
    "skipped": colors.HexColor("#f59e0b"),
    "error": colors.HexColor("#f97316"),
}
# Cap rows per table so a huge plan cannot blow up memory / layout.
_MAX_ROWS = 400


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    base.add(
        ParagraphStyle(
            "H1Blue", parent=base["Heading1"], textColor=_DARK_BLUE, spaceAfter=8
        )
    )
    base.add(
        ParagraphStyle(
            "H2Blue", parent=base["Heading2"], textColor=_DARK_BLUE, spaceBefore=10
        )
    )
    base.add(ParagraphStyle("Cell", parent=base["BodyText"], fontSize=8, leading=10))
    base.add(
        ParagraphStyle(
            "Warn", parent=base["BodyText"], textColor=colors.HexColor("#b45309")
        )
    )
    return base


def build_pdf_report(data: dict[str, Any]) -> bytes:
    """Render the normalized run context to PDF bytes."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        title=f"Auto-AT Report — {data.get('document_name', '')}",
    )
    s = _styles()
    flow: list[Any] = []

    # 1. Title + metadata
    flow.append(Paragraph("Auto-AT — API Test Report", s["H1Blue"]))
    flow.append(Paragraph(f"Document: {data.get('document_name', '—')}", s["BodyText"]))
    flow.append(Paragraph(f"Run: {data.get('run_id', '—')}", s["BodyText"]))
    flow.append(Paragraph(f"Status: {data.get('run_status', '—')}", s["BodyText"]))
    flow.append(Paragraph(f"Generated: {data.get('generated_at', '—')}", s["BodyText"]))
    flow.append(Spacer(1, 6 * mm))

    # 2. Executive summary + metrics
    flow.append(Paragraph("Executive Summary", s["H2Blue"]))
    flow.append(Paragraph(_esc(data.get("executive_summary") or "—"), s["BodyText"]))
    metrics = [
        ["Pass Rate", f"{_num(data.get('pass_rate'))}%"],
        ["Coverage", f"{_num(data.get('coverage_percentage'))}%"],
        ["Total Tests", str(data.get("total_test_cases") or 0)],
        ["Requirements", str(len(data.get("requirements") or []))],
    ]
    flow.append(Spacer(1, 3 * mm))
    flow.append(_kv_table(metrics))

    # 3. Adaptive-planner decision
    complexity = data.get("complexity")
    if isinstance(complexity, dict):
        flow.append(Paragraph("Adaptive Planner Decision", s["H2Blue"]))
        roles = ", ".join(complexity.get("selected_roles") or []) or "—"
        flow.append(
            Paragraph(
                f"Agents selected: {complexity.get('agent_count', '—')} "
                f"(score {complexity.get('score', '—')}). Roles: {roles}.",
                s["BodyText"],
            )
        )
        if complexity.get("rationale"):
            flow.append(Paragraph(_esc(complexity["rationale"]), s["Cell"]))

    # 4. Coverage matrix + review history
    _append_review_gate(flow, s, data.get("review_gate"))
    _append_coverage_matrix(flow, s, data.get("obligations") or [], data.get("review_gate"))

    # 5. Warnings
    _append_warnings(flow, s, data)

    # 6. Test cases
    flow.append(PageBreak())
    _append_test_cases(flow, s, data.get("test_cases") or [], data.get("exec_results") or [])

    # 7. Execution results summary
    _append_execution(flow, s, data.get("execution"))

    doc.build(flow)
    return buf.getvalue()


# ── Section helpers ──────────────────────────────────────────────────────────


def _append_review_gate(flow: list, s: dict, gate: Any) -> None:
    if not isinstance(gate, dict):
        return
    flow.append(Paragraph("Senior Review Coverage Gate", s["H2Blue"]))
    flow.append(
        Paragraph(
            f"Final coverage {_num(gate.get('final_coverage_percent'))}% "
            f"(threshold {_num(gate.get('coverage_threshold_percent'))}%); "
            f"verdict {gate.get('final_verdict', '—')}; "
            f"{'EXHAUSTED' if gate.get('coverage_gate_exhausted') else 'accepted'} "
            f"after {len(gate.get('iterations') or [])} iteration(s).",
            s["BodyText"],
        )
    )
    header = ["Iter", "Cases", "Coverage %", "Verdict", "Accepted"]
    rows = [header]
    for it in (gate.get("iterations") or [])[:_MAX_ROWS]:
        cov = it.get("coverage") or {}
        rev = it.get("review") or {}
        rows.append(
            [
                str(it.get("iteration", "")),
                str(it.get("case_count", "")),
                str(_num(cov.get("coverage_percent"))),
                str(rev.get("verdict", "")),
                "yes" if it.get("accepted") else "no",
            ]
        )
    flow.append(_grid(rows, [14 * mm, 16 * mm, 26 * mm, 28 * mm, 22 * mm]))


def _append_coverage_matrix(flow: list, s: dict, obligations: list, gate: Any) -> None:
    if not obligations:
        return
    gap_ids = set()
    if isinstance(gate, dict) and gate.get("iterations"):
        sel = gate.get("selected_iteration", 0)
        for it in gate["iterations"]:
            if it.get("iteration") == sel:
                gap_ids = {
                    g.get("obligation_id") for g in (it.get("coverage") or {}).get("gaps", [])
                }
                break
    flow.append(Paragraph("Coverage Matrix (Obligations)", s["H2Blue"]))
    header = ["ID", "Kind", "Required", "Covered", "Description"]
    rows = [header]
    for o in obligations[:_MAX_ROWS]:
        required = o.get("required", True)
        covered = "—" if not required else ("no" if o.get("id") in gap_ids else "yes")
        rows.append(
            [
                str(o.get("id", "")),
                str(o.get("kind", "")),
                "yes" if required else "no",
                covered,
                Paragraph(_esc(str(o.get("description", ""))), s["Cell"]),
            ]
        )
    flow.append(_grid(rows, [22 * mm, 20 * mm, 18 * mm, 18 * mm, 76 * mm]))


def _append_warnings(flow: list, s: dict, data: dict) -> None:
    warnings = list(data.get("planner_warnings") or [])
    assumptions = list(data.get("assumptions") or [])
    if not warnings and not assumptions:
        return
    flow.append(Paragraph("Warnings & Assumptions", s["H2Blue"]))
    for w in warnings[:_MAX_ROWS]:
        flow.append(Paragraph(f"[!] {_esc(str(w))}", s["Warn"]))
    for a in assumptions[:_MAX_ROWS]:
        flow.append(Paragraph(f"- assumption: {_esc(str(a))}", s["Cell"]))


def _append_test_cases(flow: list, s: dict, cases: list, exec_results: list) -> None:
    flow.append(Paragraph("Test Cases", s["H2Blue"]))
    if not cases:
        flow.append(Paragraph("No test cases.", s["BodyText"]))
        return
    status_by_id = {
        r.get("test_case_id"): r.get("status")
        for r in exec_results
        if isinstance(r, dict)
    }
    header = ["ID", "Title", "Method", "Endpoint", "Exp.", "Status"]
    rows = [header]
    for c in cases[:_MAX_ROWS]:
        rows.append(
            [
                str(c.get("id", "")),
                Paragraph(_esc(str(c.get("title", ""))), s["Cell"]),
                str(c.get("http_method") or ""),
                Paragraph(_esc(str(c.get("api_endpoint") or "")), s["Cell"]),
                str(c.get("expected_status_code") or ""),
                str(status_by_id.get(c.get("id"), "—")),
            ]
        )
    flow.append(_grid(rows, [18 * mm, 46 * mm, 16 * mm, 44 * mm, 12 * mm, 18 * mm]))
    if len(cases) > _MAX_ROWS:
        flow.append(
            Paragraph(f"… {len(cases) - _MAX_ROWS} more cases truncated.", s["Cell"])
        )


def _append_execution(flow: list, s: dict, execution: Any) -> None:
    if not isinstance(execution, dict):
        return
    summary = execution.get("summary") or {}
    flow.append(Paragraph("Execution Summary", s["H2Blue"]))
    rows = [
        ["Total", str(summary.get("total", 0))],
        ["Passed", str(summary.get("passed", 0))],
        ["Failed", str(summary.get("failed", 0))],
        ["Skipped", str(summary.get("skipped", 0))],
        ["Errors", str(summary.get("errors", 0))],
        ["Pass rate", f"{_num(summary.get('pass_rate'))}%"],
    ]
    flow.append(_kv_table(rows))


# ── Low-level table helpers ──────────────────────────────────────────────────


def _kv_table(rows: list[list[str]]) -> Table:
    t = Table(rows, colWidths=[40 * mm, 60 * mm], hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), _DARK_BLUE),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, _LIGHT_BG]),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return t


def _grid(rows: list[list[Any]], col_widths: list[float]) -> Table:
    t = Table(rows, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LIGHT_BG]),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return t


def _esc(text: str) -> str:
    """Escape characters that ReportLab Paragraph treats as markup."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _num(value: Any) -> float:
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return 0.0
