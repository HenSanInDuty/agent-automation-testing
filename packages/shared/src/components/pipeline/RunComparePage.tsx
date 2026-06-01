"use client";

import React from "react";
import Link from "next/link";
import { ArrowLeft, GitBranch } from "lucide-react";
import { RunCompareView } from "./RunCompareView";

export interface RunComparePageProps {
  templateId: string;
  runIds: string[];
  nodeIds: string[];
}

export function RunComparePage({ templateId, runIds, nodeIds }: RunComparePageProps) {
  return (
    <div className="flex flex-col gap-6 p-6 max-w-6xl mx-auto w-full">
      <div className="flex items-center gap-3">
        <Link
          href={`/pipelines/${templateId}/runs`}
          className="inline-flex items-center gap-1.5 text-sm text-[#92a4c9] hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to run history
        </Link>
      </div>

      <div className="rounded-2xl border border-[#2b3b55] bg-[#18202F] p-5">
        <div className="flex items-center gap-2 mb-4">
          <GitBranch className="w-5 h-5 text-blue-400" />
          <h1 className="text-lg font-semibold text-white">Run Comparison</h1>
        </div>
        <div className="flex flex-wrap gap-2">
          {runIds.map((id) => (
            <code
              key={id}
              className="text-[10px] font-mono text-[#92a4c9] bg-[#1e2a3d] px-2 py-1 rounded border border-[#2b3b55]"
            >
              {id.slice(0, 16)}…
            </code>
          ))}
        </div>
      </div>

      <RunCompareView runIds={runIds} nodeIds={nodeIds} />
    </div>
  );
}
