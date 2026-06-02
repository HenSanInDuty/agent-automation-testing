"use client";

import * as React from "react";
import { ArrowRightLeft, Send, Inbox } from "lucide-react";

import { Modal, ModalHeader, ModalBody } from "../../components/ui/Modal";
import { cn } from "../../lib/utils";
import type { TestCaseRow, TestExecutionDetail } from "./TestCasesTable";

// ─────────────────────────────────────────────────────────────────────────────
// JSON / text block — renders headers, bodies, responses safely.
// ─────────────────────────────────────────────────────────────────────────────

export function JsonBlock({ value }: { value: unknown }) {
  let text: string | null = null;
  if (value == null) text = null;
  else if (typeof value === "string") text = value;
  else {
    try {
      text = JSON.stringify(value, null, 2);
    } catch {
      text = String(value);
    }
  }
  if (!text || !text.trim()) {
    return <span className="text-xs text-[#5e7196]">—</span>;
  }
  return (
    <pre className="max-h-72 overflow-auto rounded-lg border border-[#22304a] bg-[#0c121d] p-3 text-[11px] leading-relaxed font-mono text-[#a8b8d4] whitespace-pre-wrap break-words">
      {text}
    </pre>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-[#5e7196]">{label}</p>
      {children}
    </div>
  );
}

function statusChip(exec?: TestExecutionDetail) {
  const s = exec?.status;
  const map: Record<string, string> = {
    passed: "text-emerald-300 bg-emerald-500/10 border-emerald-500/25",
    failed: "text-red-300 bg-red-500/10 border-red-500/25",
    error: "text-red-300 bg-red-500/10 border-red-500/25",
    skipped: "text-amber-300 bg-amber-500/10 border-amber-500/25",
  };
  const label = s ? s[0].toUpperCase() + s.slice(1) : "Pending";
  const cls = (s && map[s]) || "text-[#92a4c9] bg-[#1e2a3d] border-[#22304a]";
  return (
    <span className={cn("inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold border", cls)}>
      {label}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// TestCaseDetailModal
// ─────────────────────────────────────────────────────────────────────────────

export interface TestCaseDetailModalProps {
  open: boolean;
  onClose: () => void;
  testCase: TestCaseRow | null;
  exec?: TestExecutionDetail;
}

export function TestCaseDetailModal({ open, onClose, testCase, exec }: TestCaseDetailModalProps) {
  if (!testCase) return null;
  const tc = testCase;
  const reqLine = [tc.httpMethod, tc.apiEndpoint].filter(Boolean).join(" ");

  return (
    <Modal open={open} onClose={onClose} size="2xl">
      <ModalHeader
        title={`${tc.id} — ${tc.title}`}
        subtitle={reqLine || undefined}
        icon={<ArrowRightLeft className="w-4 h-4" />}
        onClose={onClose}
      />
      <ModalBody className="space-y-5">
        {/* Overview */}
        <div className="flex flex-wrap items-center gap-2">
          {statusChip(exec)}
          {tc.expectedStatusCode != null && (
            <span className="text-[11px] text-[#92a4c9]">Expected status: <b className="text-white">{tc.expectedStatusCode}</b></span>
          )}
          {exec?.durationMs != null && (
            <span className="text-[11px] text-[#5e7196]">{exec.durationMs.toFixed(0)} ms</span>
          )}
        </div>

        {tc.description?.trim() && (
          <Field label="Description"><p className="text-sm text-[#92a4c9]">{tc.description}</p></Field>
        )}
        {tc.preconditions?.trim() && (
          <Field label="Preconditions"><p className="text-sm text-[#92a4c9]">{tc.preconditions}</p></Field>
        )}

        {/* Steps */}
        {tc.steps && tc.steps.length > 0 && (
          <Field label="Steps">
            <ol className="space-y-1.5">
              {tc.steps.map((s, i) => (
                <li key={i} className="flex gap-2 text-xs text-[#a8b8d4]">
                  <span className="text-[#5e7196] font-mono shrink-0">{s.step_number ?? i + 1}.</span>
                  <span>
                    {s.action}
                    {s.expected_result && <span className="text-[#5e7196]"> → {s.expected_result}</span>}
                  </span>
                </li>
              ))}
            </ol>
          </Field>
        )}

        {/* Request / Response side by side */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="space-y-3 rounded-xl border border-[#22304a] bg-[#141c2c]/60 p-4">
            <p className="inline-flex items-center gap-1.5 text-xs font-semibold text-white"><Send className="w-3.5 h-3.5 text-[#5b9eff]" /> Request</p>
            {reqLine && <p className="font-mono text-xs text-[#92a4c9]">{reqLine}</p>}
            <Field label="Headers"><JsonBlock value={tc.requestHeaders} /></Field>
            <Field label="Body"><JsonBlock value={tc.requestBody} /></Field>
            {tc.expectedResult?.trim() && (
              <Field label="Expected result"><p className="text-xs text-[#a8b8d4]">{tc.expectedResult}</p></Field>
            )}
          </div>

          <div className="space-y-3 rounded-xl border border-[#22304a] bg-[#141c2c]/60 p-4">
            <p className="inline-flex items-center gap-1.5 text-xs font-semibold text-white"><Inbox className="w-3.5 h-3.5 text-emerald-400" /> Response</p>
            {exec ? (
              <>
                {exec.actualStatusCode != null && (
                  <p className="text-xs text-[#92a4c9]">Status: <b className="text-white">{exec.actualStatusCode}</b></p>
                )}
                <Field label="Response body"><JsonBlock value={exec.actualResponse} /></Field>
                {exec.actualResult?.trim() && (
                  <Field label="Result"><p className="text-xs text-[#a8b8d4]">{exec.actualResult}</p></Field>
                )}
                {exec.errorMessage?.trim() && (
                  <Field label="Error"><p className="text-xs text-red-300 font-mono whitespace-pre-wrap">{exec.errorMessage}</p></Field>
                )}
                {exec.logs && exec.logs.length > 0 && (
                  <Field label="Logs">
                    <pre className="max-h-48 overflow-auto rounded-lg border border-[#22304a] bg-[#0c121d] p-3 text-[11px] font-mono text-[#a8b8d4] whitespace-pre-wrap">{exec.logs.join("\n")}</pre>
                  </Field>
                )}
              </>
            ) : (
              <p className="text-xs text-[#5e7196]">This test case has not been executed yet.</p>
            )}
          </div>
        </div>
      </ModalBody>
    </Modal>
  );
}

export default TestCaseDetailModal;
