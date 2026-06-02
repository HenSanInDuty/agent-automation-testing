"use client";

import * as React from "react";
import {
  CheckCircle2,
  XCircle,
  Clock,
  SkipForward,
  AlertTriangle,
  ChevronRight,
  ChevronDown,
  Maximize2,
} from "lucide-react";

import { cn } from "../../lib/utils";
import { TestCaseDetailModal } from "./TestCaseDetailModal";

// ─────────────────────────────────────────────────────────────────────────────
// Types — lean view-models derived from backend TestCaseOutput / ExecutionOutput.
// ─────────────────────────────────────────────────────────────────────────────

export type ExecutionStatus = "passed" | "failed" | "skipped" | "error";

export interface TestStepRow {
  step_number?: number;
  action?: string;
  expected_result?: string;
}

export interface TestCaseRow {
  id: string;
  title: string;
  description?: string;
  /** false → not auto-runnable, shown as Skipped even without an execution result. */
  executable?: boolean;
  preconditions?: string;
  expectedResult?: string;
  steps?: TestStepRow[];
  // Planned request
  httpMethod?: string | null;
  apiEndpoint?: string | null;
  requestHeaders?: unknown;
  requestBody?: unknown;
  expectedStatusCode?: number | null;
}

export interface TestExecutionDetail {
  status: ExecutionStatus;
  actualStatusCode?: number | null;
  actualResponse?: unknown;
  actualResult?: string;
  errorMessage?: string | null;
  durationMs?: number;
  logs?: string[];
}

export interface TestCasesTableProps {
  testCases: TestCaseRow[];
  /** Map of test_case_id → execution detail (status + actual request/response). */
  executionByCaseId: Record<string, TestExecutionDetail>;
}

// ─────────────────────────────────────────────────────────────────────────────
// Status / result derivation
// ─────────────────────────────────────────────────────────────────────────────

type Cell = { label: string; cls: string; Icon: React.ComponentType<{ className?: string }> };

function deriveCells(tc: TestCaseRow, exec?: TestExecutionDetail): { status: Cell; result: Cell } {
  const dash: Cell = { label: "—", cls: "text-[#5e7196]", Icon: () => null as never };
  const s = exec?.status;

  // Backend TestCase.executable defaults to false and is set true only for
  // auto-runnable cases — so a case with no execution result is "Pending" only
  // when runnable, otherwise "Skipped".
  if (!s) {
    if (tc.executable === false) {
      return { status: { label: "Skipped", cls: "text-amber-300 bg-amber-500/10 border-amber-500/25", Icon: SkipForward }, result: dash };
    }
    return { status: { label: "Pending", cls: "text-[#92a4c9] bg-[#1e2a3d] border-[#22304a]", Icon: Clock }, result: dash };
  }

  const executed: Cell = { label: "Executed", cls: "text-blue-300 bg-blue-500/10 border-blue-500/25", Icon: CheckCircle2 };
  switch (s) {
    case "passed":
      return { status: executed, result: { label: "Pass", cls: "text-emerald-300 bg-emerald-500/10 border-emerald-500/25", Icon: CheckCircle2 } };
    case "failed":
      return { status: executed, result: { label: "Failed", cls: "text-red-300 bg-red-500/10 border-red-500/25", Icon: XCircle } };
    case "error":
      return { status: executed, result: { label: "Error", cls: "text-red-300 bg-red-500/10 border-red-500/25", Icon: AlertTriangle } };
    case "skipped":
    default:
      return { status: { label: "Skipped", cls: "text-amber-300 bg-amber-500/10 border-amber-500/25", Icon: SkipForward }, result: dash };
  }
}

function Badge({ cell }: { cell: Cell }) {
  const { label, cls, Icon } = cell;
  return (
    <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border whitespace-nowrap", cls)}>
      <Icon className="w-3 h-3" />
      {label}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Quick-peek row (inline expand) — compact request/response summary.
// ─────────────────────────────────────────────────────────────────────────────

function QuickPeek({ tc, exec, onOpenDetails }: { tc: TestCaseRow; exec?: TestExecutionDetail; onOpenDetails: () => void }) {
  const reqLine = [tc.httpMethod, tc.apiEndpoint].filter(Boolean).join(" ") || "—";
  const respShort =
    exec == null
      ? "Not executed yet"
      : [exec.actualStatusCode != null ? `${exec.actualStatusCode}` : null, exec.errorMessage || exec.actualResult || ""]
          .filter(Boolean)
          .join("  ");
  return (
    <div className="px-4 py-3 bg-[#0c121d] border-t border-[#22304a] space-y-2">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="text-xs">
          <span className="text-[#5e7196]">Request:</span>{" "}
          <span className="font-mono text-[#a8b8d4]">{reqLine}</span>
          {tc.expectedStatusCode != null && <span className="text-[#5e7196]"> (expects {tc.expectedStatusCode})</span>}
        </div>
        <div className="text-xs min-w-0">
          <span className="text-[#5e7196]">Response:</span>{" "}
          <span className="font-mono text-[#a8b8d4] break-words line-clamp-2 align-top">{respShort || "—"}</span>
        </div>
      </div>
      <button
        type="button"
        onClick={onOpenDetails}
        className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-lg text-[11px] font-medium bg-[#1e2a3d] hover:bg-[#263450] text-[#92a4c9] hover:text-white border border-[#22304a] transition-colors"
      >
        <Maximize2 className="w-3 h-3" /> View full details
      </button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// TestCasesTable
// ─────────────────────────────────────────────────────────────────────────────

export function TestCasesTable({ testCases, executionByCaseId }: TestCasesTableProps) {
  const [expandedId, setExpandedId] = React.useState<string | null>(null);
  const [detailCase, setDetailCase] = React.useState<TestCaseRow | null>(null);

  // Count only cases that actually ran (skipped doesn't count).
  const executedCount = testCases.filter((t) => {
    const s = executionByCaseId[t.id]?.status;
    return s === "passed" || s === "failed" || s === "error";
  }).length;

  return (
    <div className="rounded-xl border border-[#2b3b55] bg-[#101622]/40 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-[#2b3b55] text-xs text-[#92a4c9]">
        <span className="font-semibold text-white">{testCases.length}</span> test cases
        <span className="text-[#3d5070]">·</span>
        <span>{executedCount} executed</span>
        <span className="ml-auto text-[10px] text-[#5e7196]">Click a row to peek · open for full request/response</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-[#2b3b55] bg-[#101622]/60">
              <th className="w-8 px-2 py-2.5" />
              <th className="px-3 py-2.5 text-[11px] font-semibold text-[#3d5070] uppercase tracking-wider whitespace-nowrap">ID</th>
              <th className="px-3 py-2.5 text-[11px] font-semibold text-[#3d5070] uppercase tracking-wider">Name</th>
              <th className="px-3 py-2.5 text-[11px] font-semibold text-[#3d5070] uppercase tracking-wider">Description</th>
              <th className="px-3 py-2.5 text-[11px] font-semibold text-[#3d5070] uppercase tracking-wider whitespace-nowrap">Status</th>
              <th className="px-3 py-2.5 text-[11px] font-semibold text-[#3d5070] uppercase tracking-wider whitespace-nowrap">Result</th>
            </tr>
          </thead>
          <tbody>
            {testCases.map((tc) => {
              const exec = executionByCaseId[tc.id];
              const { status, result } = deriveCells(tc, exec);
              const isOpen = expandedId === tc.id;
              return (
                <React.Fragment key={tc.id}>
                  <tr
                    onClick={() => setExpandedId(isOpen ? null : tc.id)}
                    className={cn("border-b border-[#2b3b55]/60 cursor-pointer transition-colors align-top", isOpen ? "bg-[#18202F]" : "hover:bg-[#18202F]")}
                  >
                    <td className="px-2 py-2.5 text-[#5e7196]">
                      {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                    </td>
                    <td className="px-3 py-2.5 font-mono text-xs text-[#92a4c9] whitespace-nowrap">{tc.id}</td>
                    <td className="px-3 py-2.5 text-sm text-white max-w-xs">{tc.title}</td>
                    <td className="px-3 py-2.5 text-xs text-[#92a4c9] max-w-md">
                      {tc.description?.trim() ? tc.description : <span className="text-[#3d5070]">—</span>}
                    </td>
                    <td className="px-3 py-2.5"><Badge cell={status} /></td>
                    <td className="px-3 py-2.5"><Badge cell={result} /></td>
                  </tr>
                  {isOpen && (
                    <tr>
                      <td colSpan={6} className="p-0">
                        <QuickPeek tc={tc} exec={exec} onOpenDetails={() => setDetailCase(tc)} />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <TestCaseDetailModal
        open={detailCase !== null}
        onClose={() => setDetailCase(null)}
        testCase={detailCase}
        exec={detailCase ? executionByCaseId[detailCase.id] : undefined}
      />
    </div>
  );
}

export default TestCasesTable;
