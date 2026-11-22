import { cn } from "@/lib/utils";

export function CodeBlock({ children, className }: { children: string; className?: string }) {
  return (
    <pre
      tabIndex={0}
      className={cn(
        "max-h-96 overflow-auto rounded-lg border bg-muted p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap break-all",
        className,
      )}
    >
      {children}
    </pre>
  );
}

export function SubHeading({ children }: { children: string }) {
  return <h3 className="mt-5 mb-2 text-sm font-semibold first:mt-0">{children}</h3>;
}

export function BulletList({ items }: { items: Array<string | React.ReactNode> }) {
  return (
    <ul className="list-disc space-y-1.5 pl-5 text-sm marker:text-muted-foreground">
      {items.map((entry, index) => <li key={index}>{entry}</li>)}
    </ul>
  );
}
