import type { ReactNode } from "react";

import { Card } from "@/components/ui/card";
import type { Run } from "../../run-api";
import { StatusBadge } from "../../components/status-badge";

function Stat({ label, children, title }: { label: string; children: ReactNode; title?: string }) {
  return (
    <Card className="min-w-0 gap-1 px-3 py-3 sm:px-4">
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="min-w-0 truncate text-sm font-medium" title={title}>{children}</dd>
    </Card>
  );
}

export function RunSummary({ item, evidenceCount, actionCount }: { item: Run; evidenceCount: number; actionCount: number }) {
  const test = item.test_case_name ?? item.test_case_id;
  return (
    <section aria-label="Result">
      <dl className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Stat label="Status"><StatusBadge status={item.status} /></Stat>
        <Stat label="Test" title={test}>{test}</Stat>
        <Stat label="Revision" title={item.revision}><code className="font-mono text-xs">{item.revision}</code></Stat>
        <Stat label="Correlation ID" title={item.correlation_id}><code className="font-mono text-xs">{item.correlation_id}</code></Stat>
        {item.target_type && <Stat label="Target">{item.target_type}</Stat>}
        {item.target_url && <Stat label="Target URL" title={item.target_url}>{item.target_url}</Stat>}
        {item.created_at && <Stat label="Created">{new Date(item.created_at).toLocaleString()}</Stat>}
        <Stat label="Evidence">{evidenceCount} artifacts / {actionCount} clicks</Stat>
      </dl>
      {item.terminal_summary && (
        <p className="mt-3 rounded-lg border bg-card p-4 text-sm">
          <span className="font-medium">Terminal summary: </span>
          {item.terminal_summary}
        </p>
      )}
    </section>
  );
}
