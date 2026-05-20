/**
 * ReportVerificationCard
 * ──────────────────────
 * Card that surfaces the 3-component verification result for a run that uses
 * the `automation-testing-api` pipeline template. Renders:
 *   - Badge per component (test_cases / results / unit_test_files) with count + ✓/✗
 *   - Collapsible Issues list
 *   - Download HTML / DOCX buttons (disabled when verification has not passed)
 *
 * Pure presentational + thin hook usage. No app-specific state.
 */
"use client";

import { useState } from "react";

import { pipelineApi } from "../../api/client";
import { useReportVerification } from "../../hooks/useReportVerification";
import type {
  ReportVerificationComponent,
  ReportVerificationResponse,
} from "../../types";

export interface ReportVerificationCardProps {
  runId: string;
  /** Override polling interval (ms). null to disable. Default 5000. */
  pollIntervalMs?: number | null;
  /** Show ?force=true admin override button. Default false. */
  allowForceDownload?: boolean;
  className?: string;
}

const COMPONENT_LABELS: Record<string, string> = {
  test_cases: "Test cases",
  results: "Execution results",
  unit_test_files: "Unit test files",
};

export function ReportVerificationCard({
  runId,
  pollIntervalMs = 5_000,
  allowForceDownload = false,
  className,
}: ReportVerificationCardProps) {
  const { data, isLoading, error, refetch } = useReportVerification({
    runId,
    refetchInterval: pollIntervalMs,
  });
  const [issuesOpen, setIssuesOpen] = useState(false);

  if (isLoading) {
    return (
      <div className={className}>
        <p>Đang kiểm tra báo cáo…</p>
      </div>
    );
  }
  if (error) {
    return (
      <div className={className}>
        <p style={{ color: "crimson" }}>
          Không tải được kết quả verification: {(error as Error).message}
        </p>
        <button type="button" onClick={() => refetch()}>
          Thử lại
        </button>
      </div>
    );
  }

  const verification: ReportVerificationResponse | undefined = data;
  const verified = Boolean(verification?.verified);
  const components = verification?.components ?? {};
  const available = verification?.available !== false;

  const allIssues: string[] = [];
  for (const k of Object.keys(components)) {
    const c = components[k];
    if (c && !c.ok) {
      for (const issue of c.issues || []) {
        allIssues.push(`${COMPONENT_LABELS[k] ?? k}: ${issue}`);
      }
    }
  }

  const buildDisabled = !available || !verified;
  const tooltip = buildDisabled
    ? allIssues[0] ??
      "Report chưa được verify — không thể tải xuống."
    : "Tải báo cáo đã được verify.";

  return (
    <section
      className={className}
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: 8,
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}
    >
      <header style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <strong>Report Verification</strong>
        <span
          style={{
            padding: "2px 8px",
            borderRadius: 999,
            background: verified ? "#dcfce7" : "#fee2e2",
            color: verified ? "#166534" : "#991b1b",
            fontSize: 12,
            fontWeight: 600,
          }}
        >
          {verified ? "✅ Verified" : available ? "❌ Failed" : "⏳ Pending"}
        </span>
      </header>

      <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 4 }}>
        {(["test_cases", "results", "unit_test_files"] as const).map((key) => {
          const c: ReportVerificationComponent | undefined = components[key];
          return (
            <li
              key={key}
              style={{ display: "flex", justifyContent: "space-between" }}
            >
              <span>
                {c?.ok ? "✓" : "✗"} {COMPONENT_LABELS[key]}
              </span>
              <span style={{ color: "#6b7280" }}>
                {c ? `count=${c.count}` : "—"}
              </span>
            </li>
          );
        })}
      </ul>

      {allIssues.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => setIssuesOpen((v) => !v)}
            style={{
              background: "transparent",
              border: 0,
              color: "#2563eb",
              cursor: "pointer",
              padding: 0,
            }}
          >
            {issuesOpen ? "Ẩn" : "Xem"} {allIssues.length} vấn đề
          </button>
          {issuesOpen && (
            <ul style={{ marginTop: 6 }}>
              {allIssues.map((m, idx) => (
                <li key={idx} style={{ color: "#b91c1c" }}>
                  {m}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <footer style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <DownloadButton
          label="Tải HTML"
          href={pipelineApi.getExportHtmlUrl(runId)}
          disabled={buildDisabled}
          tooltip={tooltip}
        />
        <DownloadButton
          label="Tải DOCX"
          href={pipelineApi.getExportDocxUrl(runId)}
          disabled={buildDisabled}
          tooltip={tooltip}
        />
        {allowForceDownload && buildDisabled && (
          <>
            <DownloadButton
              label="Tải HTML (force)"
              href={`${pipelineApi.getExportHtmlUrl(runId)}?force=true`}
              disabled={false}
              tooltip="Admin override — bỏ qua verifier"
            />
            <DownloadButton
              label="Tải DOCX (force)"
              href={`${pipelineApi.getExportDocxUrl(runId)}?force=true`}
              disabled={false}
              tooltip="Admin override — bỏ qua verifier"
            />
          </>
        )}
      </footer>
    </section>
  );
}

interface DownloadButtonProps {
  label: string;
  href: string;
  disabled: boolean;
  tooltip: string;
}

function DownloadButton({ label, href, disabled, tooltip }: DownloadButtonProps) {
  if (disabled) {
    return (
      <button
        type="button"
        title={tooltip}
        aria-disabled
        disabled
        style={{
          padding: "6px 12px",
          borderRadius: 6,
          border: "1px solid #e5e7eb",
          background: "#f3f4f6",
          color: "#9ca3af",
          cursor: "not-allowed",
        }}
      >
        {label}
      </button>
    );
  }
  return (
    <a
      href={href}
      title={tooltip}
      style={{
        padding: "6px 12px",
        borderRadius: 6,
        border: "1px solid #2563eb",
        background: "#2563eb",
        color: "#ffffff",
        textDecoration: "none",
      }}
    >
      {label}
    </a>
  );
}
