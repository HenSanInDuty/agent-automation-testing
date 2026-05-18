"use client";

import { useParams } from "next/navigation";
import { PipelineRunHistoryPage } from "@auto-at/shared";

export default function UserPipelineRunsPage() {
  const params = useParams();
  const templateId = typeof params.id === "string" ? params.id : (params.id?.[0] ?? "");

  return (
    <div className="max-w-6xl mx-auto px-4 py-6">
      <PipelineRunHistoryPage templateId={templateId} />
    </div>
  );
}
