"use client";

import { useParams } from "next/navigation";
import { PipelineRunPage } from "@auto-at/shared";

export default function UserPipelineRunPage() {
  const params = useParams();
  const templateId = typeof params.id === "string" ? params.id : (params.id?.[0] ?? "");

  return (
    <div className="max-w-6xl mx-auto px-4 py-6">
      {/* Simplified end-user mode: no LLM profile / run-control choices, results shown inline.
          DAG visualization stays admin-only (requires React Flow + builder nodes). */}
      <PipelineRunPage
        templateId={templateId}
        hideLlmProfile
        hideRunControls
        showResultsInline
        hideNodeResults
      />
    </div>
  );
}
