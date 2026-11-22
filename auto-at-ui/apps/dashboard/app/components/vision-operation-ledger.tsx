"use client";

import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { VisualLocator, VisualOperation, VisionHandoffBranch } from "../generation-types";
import { CheckboxField, Disclosure, Hint, Panel } from "./agent-ui";
import { operationLabel, operationStatus } from "./vision-operation-model";
import { agentStepView } from "./vision-provider-model";

export function VisionOperationLedger({ items, locators, branches, selectedId, onSelect, follow, onFollow }: {
  items: VisualOperation[]; locators: VisualLocator[];
  branches: VisionHandoffBranch[]; selectedId: string | null; onSelect: (id: string) => void;
  follow: boolean; onFollow: (value: boolean) => void;
}) {
  const [branchId, setBranchId] = useState<string | null>(null);
  const [showRestore, setShowRestore] = useState(true);
  const positionId = useId();
  const branch = branches.find((b) => b.id === branchId);
  const visible = items.filter((item) => (!branch || branch.steps.some((step) => step.operation_id === item.id)) && (showRestore || !["restore", "replay"].includes(item.purpose)));
  const selected = items.find((item) => item.id === selectedId);
  const index = visible.findIndex((item) => item.id === selectedId);
  const locator = locators.find((item) => item.id === selected?.locator_id);
  const agent = selected ? agentStepView(selected) : null;
  return <Panel aria-label="Operation trace" tabIndex={0} title="Browser steps"
    className="outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 min-[900px]:h-[clamp(28rem,40vw,34rem)]"
    actions={<CheckboxField checked={follow} onCheckedChange={(checked) => { setBranchId(null); onFollow(checked); }}>Follow live</CheckboxField>}
    onKeyDown={(event) => {
      if ((event.target as HTMLElement).closest("input,textarea,select,[contenteditable=true]")) return;
      const next = event.key === "Home" ? 0 : event.key === "End" ? visible.length - 1 : event.key === "ArrowLeft" ? Math.max(0, index - 1) : event.key === "ArrowRight" ? Math.min(visible.length - 1, index + 1) : null;
      if (next !== null && visible[next]) { event.preventDefault(); onSelect(visible[next].id); }
    }}>
    <Disclosure variant="plain" title="Filter steps" className="shrink-0 text-xs [&[open]]:max-h-40 [&[open]]:overflow-auto" bodyClassName="space-y-3 text-xs">
      <CheckboxField checked={showRestore} onCheckedChange={setShowRestore}>Show restoration</CheckboxField>
      {branches.length > 0 && <div className="flex flex-wrap gap-1.5" role="group" aria-label="Recorded branches">
        <Button type="button" size="xs" variant="outline" onClick={() => setBranchId(null)}>All operations</Button>
        {branches.map((item, i) => <Button type="button" size="xs" variant={item.id === branchId ? "secondary" : "outline"} key={item.id} aria-pressed={item.id === branchId} onClick={() => { setBranchId(item.id); const id = item.steps.at(-1)?.operation_id; if (id) onSelect(id); }}>Branch {i + 1}{item.status === "blocked" ? ` · ${item.reason_code?.replaceAll("_", " ")}` : ""}</Button>)}
      </div>}
    </Disclosure>
    {visible.length ? <>
      <ol className="-mx-1 flex max-h-80 min-h-0 flex-1 flex-col gap-1 overflow-y-auto p-1 scrollbar-thin min-[900px]:max-h-none">
        {visible.map((item) => {
          const current = item.id === selectedId;
          return <li key={item.id}>
            <button type="button" aria-label={`View operation ${item.sequence} ${item.action_kind}`} aria-current={current ? "step" : undefined}
              className="flex w-full items-start gap-3 rounded-lg border border-transparent p-2.5 text-left text-sm outline-none transition-colors hover:bg-muted focus-visible:ring-[3px] focus-visible:ring-ring/50 aria-[current=step]:border-primary/30 aria-[current=step]:bg-accent aria-[current=step]:ring-2 aria-[current=step]:ring-primary/50"
              onClick={() => onSelect(item.id)}>
              <span className={cn("grid size-6 shrink-0 place-items-center rounded-full text-xs font-medium tabular-nums", current ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground")}>{item.sequence}</span>
              <span className="min-w-0">
                <strong className="block text-sm font-medium [overflow-wrap:anywhere]">{operationLabel(item, locators.find((locator) => locator.id === item.locator_id))}</strong>
                <small className="mt-0.5 block text-xs text-muted-foreground">{operationStatus(item.status)}{["restore", "replay"].includes(item.purpose) && " · Returning to an earlier page"}</small>
              </span>
            </button>
          </li>;
        })}
      </ol>
      <label htmlFor={positionId} className="grid shrink-0 gap-1 text-xs text-muted-foreground">Step position
        <input id={positionId} type="range" aria-label="Trace position" className="block w-full accent-primary" min={0} max={Math.max(0, visible.length - 1)} value={Math.max(0, index)} onChange={(event) => onSelect(visible[Number(event.target.value)].id)} />
      </label>
    </> : <Hint className="py-4 text-center">No browser action has been recorded yet.</Hint>}
    {selected && <div className="shrink-0 rounded-lg border bg-muted/40 px-3 py-2 text-xs" aria-label="Selected operation">
      <strong className="block text-sm font-medium [overflow-wrap:anywhere]">Operation {selected.sequence}: {operationLabel(selected, locator)}</strong>
      <p className="mt-0.5 text-muted-foreground">{operationStatus(selected.status)}</p>
      {agent && <div aria-label="Agent step" className="mt-2 min-w-0 [overflow-wrap:anywhere]">
        <dl className="grid gap-x-3 gap-y-1 min-[480px]:grid-cols-[auto_1fr]"><dt className="font-medium">Đánh giá bước trước</dt><dd className="text-muted-foreground">{agent.previous}</dd><dt className="font-medium">Memory</dt><dd className="text-muted-foreground">{agent.memory}</dd><dt className="font-medium">Mục tiêu kế</dt><dd className="text-muted-foreground">{agent.next}</dd></dl>
        {agent.blocked.length > 0 && <><p className="mt-2 font-medium">Blocked</p><ul className="list-disc pl-4 text-muted-foreground">{agent.blocked.map((line, index) => <li key={index}>{line}</li>)}</ul></>}
      </div>}
    </div>}
  </Panel>;
}
