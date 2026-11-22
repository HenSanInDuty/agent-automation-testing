import type { ComponentProps, ReactNode } from "react";
import { CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * Standard titled panel for dashboard pages: a card-styled <section> with heading, optional description
 * and actions. Use `contentClassName` for the body layout; pass `aria-label` when there is no visible title.
 */
export function Section({ title, description, actions, children, className, contentClassName, ...props }: Omit<ComponentProps<"section">, "title"> & {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  contentClassName?: string;
}) {
  return <section data-slot="card" className={cn("flex min-w-0 flex-col gap-5 rounded-xl border bg-card py-6 text-card-foreground shadow-xs", className)} {...props}>
    {(title || description || actions) && <CardHeader className="max-sm:has-data-[slot=card-action]:grid-cols-1">
      {title && <CardTitle><h2 className="text-base font-semibold tracking-tight">{title}</h2></CardTitle>}
      {description && <CardDescription>{description}</CardDescription>}
      {actions && <CardAction className="flex flex-wrap items-center gap-2 max-sm:col-start-1 max-sm:row-span-1 max-sm:row-start-auto max-sm:justify-self-start">{actions}</CardAction>}
    </CardHeader>}
    <CardContent className={cn("min-w-0", contentClassName)}>{children}</CardContent>
  </section>;
}
