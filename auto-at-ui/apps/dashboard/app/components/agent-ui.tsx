"use client";

import { ChevronRight } from "lucide-react";
import { useId, type ComponentProps, type ReactNode } from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

/** Compact card used by the live workspace; the body is a flex column so children can fill the height. */
export function Panel({ title, actions, children, className, bodyClassName, ...props }: Omit<ComponentProps<"section">, "title"> & {
  title: ReactNode; actions?: ReactNode; bodyClassName?: string;
}) {
  return <section className={cn("flex min-w-0 flex-col overflow-hidden rounded-xl border bg-card text-card-foreground shadow-xs", className)} {...props}>
    <div className="flex min-h-12 flex-wrap items-center justify-between gap-x-3 gap-y-1 px-4 pt-3 pb-2">
      <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
      {actions}
    </div>
    <div className={cn("flex min-h-0 min-w-0 flex-1 flex-col gap-3 px-4 pb-4", bodyClassName)}>{children}</div>
  </section>;
}

/**
 * Native <details>/<summary> disclosure (the Playwright specs drive the <summary>), styled with a rotating chevron.
 * `card` renders a bordered panel; `plain` is for nested, lightweight disclosures.
 */
export function Disclosure({ title, children, variant = "card", className, bodyClassName, ...props }: Omit<ComponentProps<"details">, "title"> & {
  title: ReactNode; variant?: "card" | "plain"; bodyClassName?: string;
}) {
  const card = variant === "card";
  return <details className={cn("group min-w-0", card && "rounded-xl border bg-card text-card-foreground shadow-xs", className)} {...props}>
    <summary className={cn(
      "flex cursor-pointer list-none items-center gap-2 rounded-lg text-sm font-medium outline-none select-none marker:content-none [&::-webkit-details-marker]:hidden focus-visible:ring-[3px] focus-visible:ring-ring/50",
      card ? "px-5 py-3.5 text-base font-semibold tracking-tight hover:bg-accent/50 group-open:rounded-b-none" : "py-1 text-muted-foreground hover:text-foreground",
    )}>
      <ChevronRight className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-90" aria-hidden="true" />
      <span className="min-w-0 [overflow-wrap:anywhere]">{title}</span>
    </summary>
    <div className={cn("min-w-0 space-y-4 text-sm", card ? "border-t px-5 py-5" : "pt-2 pl-6", bodyClassName)}>{children}</div>
  </details>;
}

const noticeTones = {
  info: "border-info/30 bg-info/10 border-l-info",
  warning: "border-warning/40 bg-warning/10 border-l-warning",
  danger: "border-destructive/30 bg-destructive/10 border-l-destructive",
  success: "border-success/30 bg-success/10 border-l-success",
  neutral: "border-border bg-muted/50 border-l-muted-foreground",
} as const;

/** Inline banner: tinted by tone, accent on the left edge. Pass `role` where assistive tech must announce it. */
export function Notice({ tone = "neutral", className, ...props }: ComponentProps<"div"> & { tone?: keyof typeof noticeTones }) {
  return <div className={cn("min-w-0 rounded-lg border border-l-4 px-3.5 py-2.5 text-sm [overflow-wrap:anywhere]", noticeTones[tone], className)} {...props} />;
}

export function Code({ className, ...props }: ComponentProps<"code">) {
  return <code className={cn("rounded bg-muted px-1.5 py-0.5 font-mono text-xs break-all text-foreground", className)} {...props} />;
}

export function CodeBlock({ children, label = "Code", className }: { children: string; label?: string; className?: string }) {
  return <pre aria-label={label} className={cn("max-h-96 overflow-auto rounded-lg border bg-muted p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap [overflow-wrap:anywhere] text-foreground", className)}><code>{children}</code></pre>;
}

/** Muted explanatory text. */
export function Hint({ className, ...props }: ComponentProps<"p">) {
  return <p className={cn("text-sm text-pretty text-muted-foreground", className)} {...props} />;
}

/** Radix checkbox with a properly associated label (role=checkbox, accessible name = label text). */
export function CheckboxField({ checked, onCheckedChange, disabled, children, className }: {
  checked: boolean; onCheckedChange: (checked: boolean) => void; disabled?: boolean; children: ReactNode; className?: string;
}) {
  const id = useId();
  return <div className={cn("flex items-start gap-2.5", className)}>
    <Checkbox id={id} checked={checked} disabled={disabled} onCheckedChange={(next) => onCheckedChange(next === true)} className="mt-0.5" />
    <Label htmlFor={id} className="items-start text-sm leading-snug font-normal text-pretty">{children}</Label>
  </div>;
}

/** Labelled form control; the child must receive the same `id`. */
export function FormField({ label, id, children, className }: { label: ReactNode; id: string; children: ReactNode; className?: string }) {
  return <div className={cn("grid min-w-0 gap-2 [&_[data-slot=native-select-wrapper]]:w-full", className)}>
    <Label htmlFor={id}>{label}</Label>
    {children}
  </div>;
}

/** Simple vertical list with consistent rhythm. */
export function ItemList({ className, ...props }: ComponentProps<"ul">) {
  return <ul className={cn("grid gap-2 text-sm", className)} {...props} />;
}
