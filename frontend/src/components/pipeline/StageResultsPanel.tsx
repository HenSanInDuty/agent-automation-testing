"use client";

import * as React from "react";
import { CheckCircle2, ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useStageResults } from "@/hooks/usePipeline";

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────────────────
// Types from API responses
// ─────────────────────────────────────────────────────────────────────────────

interface Requirement {
  id?: string;
  text?: string;
  title?: string;
  description?: string;
  [key: string]: unknown;
}

interface IngestionOutput {
  total_requirements?: number;
  chunks_processed?: number;
  processing_notes?: string[];
  requirements?: Requirement[];
  [key: string]: unknown;
}

interface TestCase {
  id?: string;
  title?: string;
  description?: string;
  steps?: string[];
  expected_result?: string;
  [key: string]: unknown;
}

interface TestCaseOutput {
  total_test_cases?: number;
  coverage_summary?: { coverage_percentage?: number };
  test_cases?: TestCase[];
  [key: string]: unknown;
}

interface TestResult {
  test_case_id?: string;
  title?: string;
  status?: string;
  error_message?: string;
  [key: string]: unknown;
}

interface ExecutionOutput {
  summary?: {
    total?: number;
    passed?: number;
    failed?: number;
    pass_rate?: number;
  };
  results?: TestResult[];
  [key: string]: unknown;
}

interface ReportingOutput {
  coverage_percentage?: number;
  pass_rate?: number;
  executive_summary?: string;
  recommendations?: string[];
  [key: string]: unknown;
}

// ─────────────────────────────────────────────────────────────────────────────
// Small helpers
// ─────────────────────────────────────────────────────────────────────────────

function MetricCard({
  label,
  value,
}: {
  label: string;
  value: string | number | undefined;
}) {
  return (
    <div className="bg-[#1e2a3d] border border-[#2b3b55] rounded-lg px-3 py-2.5 text-center">
      <p className="text-lg font-bold text-white">{value ?? "–"}</p>
      <p className="text-[11px] text-[#92a4c9] mt-0.5">{label}</p>
    </div>
  );
}

function SkeletonCard() {
  return (
    <div className="border border-[#2b3b55] rounded-lg p-4 animate-pulse">
      <div className="flex items-center justify-between mb-3">
        <div className="h-4 w-40 bg-[#2b3b55] rounded" />
        <div className="h-5 w-20 bg-[#2b3b55] rounded-full" />
      </div>
      <div className="grid grid-cols-3 gap-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-14 bg-[#2b3b55] rounded-lg" />
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Stage-specific sub-components
// ─────────────────────────────────────────────────────────────────────────────

function RequirementsTable({ requirements }: { requirements: Requirement[] }) {
  if (!requirements.length) return null;
  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full text-xs text-[#92a4c9] border-collapse">
        <thead>
          <tr className="border-b border-[#2b3b55]">
            <th className="text-left py-1.5 pr-3 font-medium text-[#5b9eff]">
              #
            </th>
            <th className="text-left py-1.5 font-medium text-[#5b9eff]">
              Requirement
            </th>
          </tr>
        </thead>
        <tbody>
          {requirements.slice(0, 20).map((req, i) => (
            <tr key={req.id ?? i} className="border-b border-[#1e2a3d]">
              <td className="py-1.5 pr-3 text-[#3d5070] font-mono">{i + 1}</td>
              <td className="py-1.5 text-[#92a4c9]">
                {req.text ??
                  req.title ??
                  req.description ??
                  JSON.stringify(req)}
              </td>
            </tr>
          ))}
          {requirements.length > 20 && (
            <tr>
              <td colSpan={2} className="py-1.5 text-[#3d5070] italic">
                … and {requirements.length - 20} more
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function IngestionResults({ data }: { data: IngestionOutput }) {
  const [expanded, setExpanded] = React.useState(false);
  const reqs = data.requirements ?? [];
  const notes = data.processing_notes ?? [];

  return (
    <div>
      <div className="grid grid-cols-3 gap-3 mb-3">
        <MetricCard
          label="Requirements Found"
          value={data.total_requirements}
        />
        <MetricCard label="Chunks Processed" value={data.chunks_processed} />
        <MetricCard label="Processing Notes" value={notes.length} />
      </div>
      {reqs.length > 0 && (
        <button
          type="button"
          onClick={() => setExpanded((p) => !p)}
          className="flex items-center gap-1.5 text-xs text-[#5b9eff] hover:text-white transition-colors"
        >
          {expanded ? (
            <ChevronDown className="w-3 h-3" />
          ) : (
            <ChevronRight className="w-3 h-3" />
          )}
          View {reqs.length} requirement{reqs.length !== 1 ? "s" : ""}
        </button>
      )}
      {expanded && <RequirementsTable requirements={reqs} />}
    </div>
  );
}

function TestCaseResults({ data }: { data: TestCaseOutput }) {
  const [expanded, setExpanded] = React.useState(false);
  const cases = data.test_cases ?? [];
  const coverage =
    data.coverage_summary?.coverage_percentage ??
    (data as Record<string, unknown>).coverage_percentage;

  return (
    <div>
      <div className="grid grid-cols-3 gap-3 mb-3">
        <MetricCard label="Test Cases" value={data.total_test_cases} />
        <MetricCard
          label="Coverage"
          value={
            coverage != null ? `${Number(coverage).toFixed(1)}%` : undefined
          }
        />
        <MetricCard
          label="Generated"
          value={cases.length || data.total_test_cases}
        />
      </div>
      {cases.length > 0 && (
        <>
          <button
            type="button"
            onClick={() => setExpanded((p) => !p)}
            className="flex items-center gap-1.5 text-xs text-[#5b9eff] hover:text-white transition-colors"
          >
            {expanded ? (
              <ChevronDown className="w-3 h-3" />
            ) : (
              <ChevronRight className="w-3 h-3" />
            )}
            View {cases.length} test case{cases.length !== 1 ? "s" : ""}
          </button>
          {expanded && (
            <div className="mt-3 space-y-2">
              {cases.slice(0, 10).map((tc, i) => (
                <div
                  key={tc.id ?? i}
                  className="bg-[#1e2a3d] border border-[#2b3b55] rounded px-3 py-2"
                >
                  <p className="text-xs font-medium text-white">
                    {tc.title ?? `Test Case ${i + 1}`}
                  </p>
                  {tc.description && (
                    <p className="text-[11px] text-[#92a4c9] mt-0.5">
                      {tc.description}
                    </p>
                  )}
                </div>
              ))}
              {cases.length > 10 && (
                <p className="text-[11px] text-[#3d5070] italic">
                  … and {cases.length - 10} more
                </p>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ExecutionResults({ data }: { data: ExecutionOutput }) {
  const summary = data.summary ?? {};
  const results = data.results ?? [];
  const [expanded, setExpanded] = React.useState(false);
  const passRate =
    summary.pass_rate != null
      ? `${(summary.pass_rate * 100).toFixed(1)}%`
      : undefined;

  return (
    <div>
      <div className="grid grid-cols-4 gap-3 mb-3">
        <MetricCard label="Total" value={summary.total} />
        <MetricCard label="Passed" value={summary.passed} />
        <MetricCard label="Failed" value={summary.failed} />
        <MetricCard label="Pass Rate" value={passRate} />
      </div>
      {results.length > 0 && (
        <>
          <button
            type="button"
            onClick={() => setExpanded((p) => !p)}
            className="flex items-center gap-1.5 text-xs text-[#5b9eff] hover:text-white transition-colors"
          >
            {expanded ? (
              <ChevronDown className="w-3 h-3" />
            ) : (
              <ChevronRight className="w-3 h-3" />
            )}
            View {results.length} result{results.length !== 1 ? "s" : ""}
          </button>
          {expanded && (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-xs text-[#92a4c9] border-collapse">
                <thead>
                  <tr className="border-b border-[#2b3b55]">
                    <th className="text-left py-1.5 pr-3 font-medium text-[#5b9eff]">
                      Test
                    </th>
                    <th className="text-left py-1.5 font-medium text-[#5b9eff]">
                      Status
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {results.slice(0, 20).map((r, i) => (
                    <tr
                      key={r.test_case_id ?? i}
                      className="border-b border-[#1e2a3d]"
                    >
                      <td className="py-1.5 pr-3">
                        {r.title ?? r.test_case_id ?? `#${i + 1}`}
                      </td>
                      <td className="py-1.5">
                        <span
                          className={cn(
                            "px-1.5 py-0.5 rounded text-[10px] font-medium",
                            r.status === "passed"
                              ? "bg-emerald-500/15 text-emerald-400"
                              : "bg-red-500/15 text-red-400",
                          )}
                        >
                          {r.status ?? "unknown"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ReportingResults({ data }: { data: ReportingOutput }) {
  const coverage =
    data.coverage_percentage != null
      ? `${Number(data.coverage_percentage).toFixed(1)}%`
      : undefined;
  const passRate =
    data.pass_rate != null
      ? `${(Number(data.pass_rate) * 100).toFixed(1)}%`
      : undefined;
  const recs = data.recommendations ?? [];

  return (
    <div>
      <div className="grid grid-cols-2 gap-3 mb-3">
        <MetricCard label="Coverage" value={coverage} />
        <MetricCard label="Pass Rate" value={passRate} />
      </div>
      {data.executive_summary && (
        <div className="mt-3 bg-[#1e2a3d] border border-[#2b3b55] rounded-lg px-3 py-2.5">
          <p className="text-xs font-medium text-[#5b9eff] mb-1">
            Executive Summary
          </p>
          <p className="text-xs text-[#92a4c9] leading-relaxed">
            {data.executive_summary}
          </p>
        </div>
      )}
      {recs.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium text-[#5b9eff] mb-1.5">
            Recommendations
          </p>
          <ul className="space-y-1">
            {recs.map((rec, i) => (
              <li
                key={i}
                className="flex items-start gap-2 text-xs text-[#92a4c9]"
              >
                <span className="mt-0.5 shrink-0 text-[#3d5070]">•</span>
                {rec}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function GenericStageResults({ data }: { data: Record<string, unknown> }) {
  return (
    <div className="overflow-x-auto">
      <pre className="text-xs text-[#92a4c9] bg-[#1e2a3d] rounded-lg p-3 overflow-auto max-h-48">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// StageResultCard
// ─────────────────────────────────────────────────────────────────────────────

function StageResultCard({
  runId,
  stage,
  summary,
}: {
  runId: string;
  stage: string;
  summary?: Record<string, unknown>;
}) {
  const { data, isLoading } = useStageResults(runId, stage);
  const label = stage;

  if (isLoading) return <SkeletonCard />;

  // If fetch failed or empty, show summary-only card
  const displayData =
    (data as unknown as Record<string, unknown>) ??
    (summary ? { ...summary } : undefined);

  return (
    <div className="border border-[#2b3b55] rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-sm text-white">{label}</h3>
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-500/15 text-emerald-400">
          <CheckCircle2 className="w-3 h-3" />
          Completed
        </span>
      </div>

      {!displayData && (
        <p className="text-xs text-[#3d5070]">Results are being saved…</p>
      )}

      {displayData &&
        (() => {
          switch (stage) {
            case "ingestion":
              return <IngestionResults data={displayData as IngestionOutput} />;
            case "testcase":
              return <TestCaseResults data={displayData as TestCaseOutput} />;
            case "execution":
              return <ExecutionResults data={displayData as ExecutionOutput} />;
            case "reporting":
              return <ReportingResults data={displayData as ReportingOutput} />;
            default:
              return <GenericStageResults data={displayData} />;
          }
        })()}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// StageResultsPanel (exported)
// ─────────────────────────────────────────────────────────────────────────────

export interface StageResultsPanelProps {
  runId: string;
  completedStages: string[];
  stageSummaries?: Record<string, Record<string, unknown>>;
  /** Show a spinner for the currently-running stage */
  currentStage?: string | null;
}

export function StageResultsPanel({
  runId,
  completedStages,
  stageSummaries = {},
  currentStage,
}: StageResultsPanelProps) {
  if (completedStages.length === 0 && !currentStage) return null;

  return (
    <div className="space-y-3">
      {completedStages.map((stage) => (
        <StageResultCard
          key={stage}
          runId={runId}
          stage={stage}
          summary={stageSummaries[stage]}
        />
      ))}

      {/* Running stage spinner */}
      {currentStage && !completedStages.includes(currentStage) && (
        <div className="border border-dashed border-[#2b3b55] rounded-lg p-4">
          <div className="flex items-center gap-3">
            <Loader2 className="w-4 h-4 text-[#135bec] animate-spin shrink-0" />
            <div>
              <p className="text-sm font-medium text-white">{currentStage}</p>
              <p className="text-xs text-[#92a4c9]">Running…</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default StageResultsPanel;
