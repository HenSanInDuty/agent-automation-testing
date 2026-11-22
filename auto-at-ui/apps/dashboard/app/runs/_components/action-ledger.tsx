import { ChevronRight } from "lucide-react";

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Section } from "../../components/section";
import { browserActionFrameUrl, type BrowserAction } from "../../run-api";

export function ActionLedger({ apiUrl, runId, actions }: { apiUrl: string; runId: string; actions: BrowserAction[] }) {
  return (
    <Section
      title="Browser action ledger"
      description="Verified completed browser actions extracted from the retained Playwright trace."
    >
      {actions.length ? (
        <>
          <p className="mb-3 text-sm">
            <strong>{actions.length}/{actions.length} clicks completed.</strong>{" "}
            <span className="text-muted-foreground">Expand a click to compare its before/after frames.</span>
          </p>
          <ol className="space-y-2">
            {actions.map((action) => (
              <li key={action.sequence} className="rounded-lg border">
                <Collapsible>
                  <CollapsibleTrigger className="group flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-muted/50">
                    <ChevronRight className="size-4 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-90" aria-hidden="true" />
                    <span className="min-w-0 break-words">
                      Click {action.sequence} · <code className="font-mono text-xs">{action.element}</code>
                      {action.duration_ms !== null ? ` · ${action.duration_ms} ms` : ""}
                      {action.source_line !== null ? ` · source line ${action.source_line}` : ""}
                    </span>
                  </CollapsibleTrigger>
                  <CollapsibleContent className="border-t p-3">
                    {action.has_before_frame || action.has_after_frame ? (
                      <div className="grid gap-3 md:grid-cols-2">
                        {action.has_before_frame && (
                          <figure className="space-y-1">
                            <figcaption className="text-xs font-medium text-muted-foreground">Before</figcaption>
                            <img className="w-full rounded-md border" src={browserActionFrameUrl(apiUrl, runId, action.sequence, "before")} alt={`Before click ${action.sequence}`} />
                          </figure>
                        )}
                        {action.has_after_frame && (
                          <figure className="space-y-1">
                            <figcaption className="text-xs font-medium text-muted-foreground">After</figcaption>
                            <img className="w-full rounded-md border" src={browserActionFrameUrl(apiUrl, runId, action.sequence, "after")} alt={`After click ${action.sequence}`} />
                          </figure>
                        )}
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground">No visual frames were retained for this click.</p>
                    )}
                  </CollapsibleContent>
                </Collapsible>
              </li>
            ))}
          </ol>
        </>
      ) : (
        <p className="text-sm text-muted-foreground">No click actions were available in the retained trace.</p>
      )}
    </Section>
  );
}
