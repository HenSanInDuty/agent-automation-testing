import { ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { VisualPageInventory } from "../generation-types";
import { Disclosure, Hint, ItemList } from "./agent-ui";
import { Section } from "./section";

export function VisionPageInventoryList({ pages, live, onSelect }: {
  pages: VisualPageInventory[]; live: boolean; onSelect: (id: string) => void;
}) {
  if (!pages.length) return null;
  return <Section aria-label="Page interaction inventory" title="Pages and interactions" description="Saved URLs and controls found in each observed page state. Counts cover visible, safely identifiable controls; scrolling or opening menus can reveal more." contentClassName="grid gap-3">
    {pages.map((page, index) => {
      const completed = page.controls.filter((control) => control.status === "completed").length;
      const remaining = page.controls.filter((control) => ["pending", "queued"].includes(control.status)).length;
      return <Disclosure key={page.state_id} open={index === 0} className="bg-background shadow-none" bodyClassName="space-y-3 px-4 py-4"
        title={<span className="text-sm font-medium">{page.page_url ?? "Page URL unavailable"} — {page.controls.length} controls · {completed} performed · {remaining} remaining</span>}>
        {page.interaction_scope === "visual_buttons" && <Hint>Scope: visual buttons, including button-shaped links and custom controls. Ordinary content links are excluded.</Hint>}
        {page.interaction_scope === "buttons" && <Hint>Scope: buttons only. Links and other control types are excluded.</Hint>}
        {page.page_url && <p className="flex flex-wrap items-center gap-x-3 gap-y-1"><a className="inline-flex items-center gap-1 text-sm font-medium text-primary underline-offset-4 hover:underline" href={page.page_url} target="_blank" rel="noopener noreferrer">Open saved URL<ExternalLink className="size-3.5" aria-hidden="true" /></a> <small className="text-xs text-muted-foreground">Query parameters and fragments are omitted.</small></p>}
        {(page.truncated || page.scrollable || page.skipped_count > 0) && <Hint>Partial page inventory{page.scrollable ? ": more content can be reached by scrolling" : ""}. {page.skipped_count} controls or elements could not be safely inventoried.</Hint>}
        {!live && remaining > 0 && <Hint>{remaining} controls remain untested in this recorded state. Finishing a session does not mean every control was tested.</Hint>}
        <ItemList className="gap-1.5">{page.controls.map((control, controlIndex) => <li key={control.key} className="flex flex-wrap items-center gap-x-2.5 gap-y-1 rounded-md px-2 py-1.5 hover:bg-muted/50">
          <strong className="font-medium">{control.name || `Unnamed ${control.role} ${controlIndex + 1}`}</strong> <span className="text-muted-foreground">({control.role}) · {control.status === "queued" && !live ? "not attempted" : control.status}</span>
          {control.operation_id && <Button type="button" variant="outline" size="xs" className="ml-auto" onClick={() => onSelect(control.operation_id!)}>Show recorded action</Button>}
        </li>)}</ItemList>
      </Disclosure>;
    })}
  </Section>;
}
