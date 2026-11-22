import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { VisualLocator } from "../generation-types";
import { Code, Hint, ItemList } from "./agent-ui";
import { Section } from "./section";

export function VisionLocatorCatalog({ items, hasMore, onMore }: { items: VisualLocator[]; hasMore: boolean; onMore: () => void }) {
  return <Section aria-label="Locator catalog" title="Recorded locators" description="Verification describes the element at exploration time. Future page changes can still make a test fail." contentClassName="grid gap-4">
    {items.length ? <ItemList>{items.map((item) => <li key={item.id} className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border bg-muted/30 px-3 py-2">
      <Badge variant="outline" className={item.status === "verified" ? "border-success/30 bg-success/10 text-success" : "border-warning/40 bg-warning/10 text-foreground"}>{item.status === "verified" ? "Verified locator" : "Unresolved locator"}</Badge>
      {item.descriptor ? <Code>{item.descriptor.strategy}{item.descriptor.role ? ` ${item.descriptor.role}` : ""}: {item.descriptor.value}</Code> : <span className="text-muted-foreground">{item.reason_code?.replaceAll("_", " ")}</span>}
      {item.descriptor?.scope.map((scope, index) => <small key={index} className="text-xs text-muted-foreground"> · {scope.kind}: {scope.selector}</small>)}
    </li>)}</ItemList> : <Hint>No locator evidence is available.</Hint>}
    {hasMore && <div><Button type="button" variant="outline" size="sm" onClick={onMore}>More locators</Button></div>}
  </Section>;
}
