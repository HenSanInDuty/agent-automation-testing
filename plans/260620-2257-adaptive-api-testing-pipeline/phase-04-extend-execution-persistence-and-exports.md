---
phase: 4
title: "Extend execution persistence and exports"
status: pending
priority: P1
dependencies: [3]
---

# Phase 4: Extend execution persistence and exports

## Overview

Execute the selected plan with the existing API runner, preserve the planning/review audit in MongoDB, and add verified PDF export beside HTML/DOCX.

## Requirements

- Only schema-valid selected cases reach execution.
- Planning iterations, chosen plan, resolved config, test results, and report metadata remain queryable by `run_id`.
- HTML and PDF share the same normalized report data and verification gate.
- Export never exposes authorization/header secrets.

## Architecture

Reuse `PipelineResultDocument` node outputs; do not add a collection. The adaptive planner node stores its full audit payload, while downstream inputs carry the selected plan. Extend `ExportService._load_run_data()` once, then render HTML through existing Jinja and PDF through a focused ReportLab builder. Store artifacts in MinIO and expose gated endpoints.

## Related Code Files

- Modify: `D:/CV/auto-at/backend/app/tools/api_test_runner.py` — selected-plan schema and safe header handling.
- Modify: `D:/CV/auto-at/backend/app/core/dag_pipeline_runner.py` — persist planner audit and selected output without duplication.
- Modify: `D:/CV/auto-at/backend/app/services/export_service.py` — normalized coverage/review context and `export_pdf()`.
- Create: `D:/CV/auto-at/backend/app/services/pdf_report_builder.py` — ReportLab PDF sections.
- Modify: `D:/CV/auto-at/backend/app/crews/export_crew.py` — generate/upload HTML and PDF; retain DOCX compatibility.
- Modify: `D:/CV/auto-at/backend/app/tools/report_verifier.py` — require plan, execution, review/coverage, and requested export artifacts.
- Modify: `D:/CV/auto-at/backend/app/api/v1/pipeline/results.py` — `GET /runs/{run_id}/export/pdf` using existing gate/RBAC.
- Modify: `D:/CV/auto-at/backend/pyproject.toml`, `backend/uv.lock`, templates, storage helpers, and export tests.

## Implementation Steps

1. Define persisted audit shape and BSON-safe serialization; avoid storing duplicate full plans in every iteration edge.
2. Execute only selected cases; retain `plan_iteration` and obligation IDs on each result.
3. Redact sensitive headers before persistence, WebSocket/Kafka events, logs, and exports.
4. Extend normalized export context with complexity decision, iteration history, coverage gaps, exhaustion warning, and test results.
5. Add PDF builder using ReportLab; include summary, coverage matrix, review history, cases, results, and warnings.
6. Upload HTML/PDF to `runs/{run_id}/`, persist URLs/checksums, and gate both downloads through report verification.
7. Add API/service tests for success, missing run, unverified report, forced admin export, Unicode, large plans, and redaction.

## Success Criteria

- [ ] MongoDB reconstructs why a plan was selected and how each executed result maps to it.
- [ ] Partial execution failures remain stored and appear in both reports.
- [ ] HTML and PDF expose equivalent core data and correct MIME/disposition headers.
- [ ] Verification failure returns existing structured 409 behavior for both formats.
- [ ] No secret header value appears in MongoDB snapshots, logs, events, HTML, or PDF.
- [ ] Export and runner unit/integration tests pass.

## Risk Assessment

ExportService has LOW graph risk but shared consumers. PDF pagination and large tables can regress memory/layout; stream bounded output, test large fixtures, and keep DOCX unchanged during migration.
