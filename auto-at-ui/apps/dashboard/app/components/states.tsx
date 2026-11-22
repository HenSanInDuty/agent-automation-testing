import { AlertTriangle, Inbox } from "lucide-react";
import type { ReactNode } from "react";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";
import { stateAccessibility } from "./state-model";

type StateProps = { title: string; children?: ReactNode; action?: ReactNode; icon?: ReactNode; className?: string };

const frame = "rounded-xl border border-dashed bg-card/50 py-12";

export function EmptyState({ title, children, action, icon, className }: StateProps) {
  const accessibility = stateAccessibility("empty");
  return <Empty role="region" aria-label={accessibility.ariaLabel} className={cn(frame, className)}>
    <EmptyHeader>
      <EmptyMedia variant="icon">{icon ?? <Inbox />}</EmptyMedia>
      <EmptyTitle><h2>{title}</h2></EmptyTitle>
      {children && <EmptyDescription>{children}</EmptyDescription>}
    </EmptyHeader>
    {action && <EmptyContent>{action}</EmptyContent>}
  </Empty>;
}

export function LoadingState({ title = "Loading", className }: { title?: string; className?: string }) {
  const accessibility = stateAccessibility("loading");
  return <Empty role="region" aria-busy={accessibility.busy} aria-label={accessibility.ariaLabel} className={cn(frame, "border-solid", className)}>
    <EmptyHeader>
      <EmptyMedia><Spinner className="size-6 text-primary" /></EmptyMedia>
      <EmptyTitle><h2>{title}</h2></EmptyTitle>
      <EmptyDescription>Please wait while the control plane responds.</EmptyDescription>
    </EmptyHeader>
  </Empty>;
}

export function ErrorState({ title = "Something went wrong", children, action, className }: StateProps) {
  const accessibility = stateAccessibility("error");
  return <Empty role={accessibility.role} aria-label={accessibility.ariaLabel} className={cn(frame, "border-solid border-destructive/30 bg-destructive/5", className)}>
    <EmptyHeader>
      <EmptyMedia variant="icon" className="bg-destructive/10 text-destructive"><AlertTriangle /></EmptyMedia>
      <EmptyTitle><h2>{title}</h2></EmptyTitle>
      {children && <EmptyDescription>{children}</EmptyDescription>}
    </EmptyHeader>
    {action && <EmptyContent>{action}</EmptyContent>}
  </Empty>;
}
