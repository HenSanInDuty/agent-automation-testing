"use client";

import * as React from "react";
import {
  CheckCircle2,
  XCircle,
  Clock,
  SkipForward,
  AlertTriangle,
} from "lucide-react";

import { cn } from "../../lib/utils";

// ─────────────────────────────────────────────────────────────────────────────
// Types — lean view-models derived from the backend TestCaseOutput / ExecutionOutput.
// ─────────────────────────────────────────────────────────────────────────────

/** Execution outcome for a single test case (backend ExecutionStatus). */
export type ExecutionStatus = "passed" | "failed" | "skipped" | "error";

export interface TestCaseRow {
  id: string;
  title: string;
  description?: string;
  /** false → not auto-runnable, shown as Skipped even without an execution result. */
  executable?: boolean;
}

export interface TestCasesTableProps {
  testCases: TestCaseRow[];
  /** Map of test_case_id → execution status, from the execution stage (may be empty). */
  executionByCaseId: Record<string, ExecutionStatus>;
}

// ─────────────────────────────────────────────────────────────────────────────
// Status / result derivation
//   status: Pending (chưa chạy) | Executed (đã chạy) | Skipped (không chạy được)
//   result: Pass | Failed | Error | — (chưa có)
// ─────────────────────────────────────────────────────────────────────────────

type Cell = { label: string; cls: string; Icon: React.ComponentType<{ className?: string }> };

function deriveCells(tc: TestCaseRow, exec?: ExecutionStatus): { status: Cell; result: Cell } {
  const dash: Cell = { label: "—", cls: "text-[#5e7196]", Icon: () => null as never };

  // Backend TestCase.executable defaults to false and is set true only for
  // auto-runnable cases — so a case with no execution result is "Pending" only
  // when runnable, otherwise "Skipped".
  if (!exec) {
    // No execution result yet.
    if (tc.executable === false) {
      return {
        status: { label: "Skipped", cls: "text-amber-300 bg-amber-500/10 border-amber-500/25", Icon: SkipForward },
        result: dash,
      };
    }
    return {
      status: { label: "Pending", cls: "text-[#92a4c9] bg-[#1e2a3d] border-[#22304a]", Icon: Clock },
      result: dash,
    };
  }

  const executed: Cell = { label: "Executed", cls: "text-blue-300 bg-blue-500/10 border-blue-500/25", Icon: CheckCircle2 };

  switch (exec) {
    case "passed":
      return { status: executed, result: { label: "Pass", cls: "text-emerald-300 bg-emerald-500/10 border-emerald-500/25", Icon: CheckCircle2 } };
    case "failed":
      return { status: executed, result: { label: "Failed", cls: "text-red-300 bg-red-500/10 border-red-500/25", Icon: XCircle } };
    case "error":
      return { status: executed, result: { label: "Error", cls: "text-red-300 bg-red-500/10 border-red-500/25", Icon: AlertTriangle } };
    case "skipped":
    default:
      return {
        status: { label: "Skipped", cls: "text-amber-300 bg-amber-500/10 border-amber-500/25", Icon: SkipForward },
        result: dash,
      };
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
// TestCasesTable
// ─────────────────────────────────────────────────────────────────────────────

export function TestCasesTable({ testCases, executionByCaseId }: TestCasesTableProps) {
  // Small summary line: total + how many actually ran (skipped doesn't count).
  const executedCount = testCases.filter((t) => {
    const s = executionByCaseId[t.id];
    return s === "passed" || s === "failed" || s === "error";
  }).length;

  return (
    <div className="rounded-xl border border-[#2b3b55] bg-[#101622]/40 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-[#2b3b55] text-xs text-[#92a4c9]">
        <span className="font-semibold text-white">{testCases.length}</span> test cases
        <span className="text-[#3d5070]">·</span>
        <span>{executedCount} executed</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-[#2b3b55] bg-[#101622]/60">
              <th className="px-3 py-2.5 text-[11px] font-semibold text-[#3d5070] uppercase tracking-wider whitespace-nowrap">ID</th>
              <th className="px-3 py-2.5 text-[11px] font-semibold text-[#3d5070] uppercase tracking-wider">Name</th>
              <th className="px-3 py-2.5 text-[11px] font-semibold text-[#3d5070] uppercase tracking-wider">Description</th>
              <th className="px-3 py-2.5 text-[11px] font-semibold text-[#3d5070] uppercase tracking-wider whitespace-nowrap">Status</th>
              <th className="px-3 py-2.5 text-[11px] font-semibold text-[#3d5070] uppercase tracking-wider whitespace-nowrap">Result</th>
            </tr>
          </thead>
          <tbody>
            {testCases.map((tc) => {
              const { status, result } = deriveCells(tc, executionByCaseId[tc.id]);
              return (
                <tr key={tc.id} className="border-b border-[#2b3b55]/60 last:border-0 hover:bg-[#18202F] transition-colors align-top">
                  <td className="px-3 py-2.5 font-mono text-xs text-[#92a4c9] whitespace-nowrap">{tc.id}</td>
                  <td className="px-3 py-2.5 text-sm text-white max-w-xs">{tc.title}</td>
                  <td className="px-3 py-2.5 text-xs text-[#92a4c9] max-w-md">
                    {tc.description?.trim() ? tc.description : <span className="text-[#3d5070]">—</span>}
                  </td>
                  <td className="px-3 py-2.5"><Badge cell={status} /></td>
                  <td className="px-3 py-2.5"><Badge cell={result} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default TestCasesTable;
