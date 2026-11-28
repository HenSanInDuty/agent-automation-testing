import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { statusLabel, statusTone, type StatusTone } from "./status-model";

export { statusLabel, statusTone } from "./status-model";

const toneClasses: Record<StatusTone, { badge: string; dot: string }> = {
  neutral: { badge: "border-border bg-secondary text-secondary-foreground", dot: "bg-muted-foreground" },
  success: { badge: "border-success/25 bg-success/10 text-success", dot: "bg-success" },
  danger: { badge: "border-destructive/25 bg-destructive/10 text-destructive", dot: "bg-destructive" },
  warning: { badge: "border-warning/30 bg-warning/15 text-warning-foreground dark:text-warning", dot: "bg-warning" },
  muted: { badge: "border-border bg-muted text-muted-foreground", dot: "bg-muted-foreground/60" },
};

export function StatusBadge({ status, children, className, tone: toneOverride }: { status: string; children?: ReactNode; className?: string; tone?: StatusTone }) {
  const tone = toneOverride ?? statusTone(status);
  const live = ["running", "generating", "queued"].includes(status.toLowerCase());
  return <Badge variant="outline" data-tone={tone} className={cn("gap-1.5 capitalize", toneClasses[tone].badge, className)}>
    <span className={cn("size-1.5 rounded-full", toneClasses[tone].dot, live && "animate-pulse")} aria-hidden="true" />
    {children ?? statusLabel(status)}
  </Badge>;
}
