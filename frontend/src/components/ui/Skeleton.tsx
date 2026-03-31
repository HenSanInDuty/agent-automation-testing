import { cn } from "@/lib/utils";

// ─────────────────────────────────────────────────────────────────────────────
// Base Skeleton
// ─────────────────────────────────────────────────────────────────────────────

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton rounded", className)} aria-hidden="true" />;
}

// ─────────────────────────────────────────────────────────────────────────────
// SkeletonText – N lines of varying widths
// ─────────────────────────────────────────────────────────────────────────────

const LINE_WIDTHS = ["w-full", "w-[85%]", "w-[70%]"];

export function SkeletonText({
  lines = 3,
  className,
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-2", className)} aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          className={cn("h-4", LINE_WIDTHS[i % LINE_WIDTHS.length])}
        />
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// SkeletonCard – card-shaped skeleton with header + body
// ─────────────────────────────────────────────────────────────────────────────

export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "rounded-xl border border-[#2b3b55] bg-[#18202F] p-5 flex flex-col gap-4",
        className
      )}
      aria-hidden="true"
    >
      {/* Card header */}
      <div className="flex items-center gap-3">
        {/* Icon placeholder */}
        <Skeleton className="w-9 h-9 rounded-lg shrink-0" />
        {/* Title + subtitle */}
        <div className="flex flex-col gap-1.5 flex-1">
          <Skeleton className="h-4 w-2/5" />
          <Skeleton className="h-3 w-3/5" />
        </div>
        {/* Action placeholder */}
        <Skeleton className="h-8 w-20 rounded-lg shrink-0" />
      </div>

      {/* Divider */}
      <div className="border-t border-[#2b3b55]" />

      {/* Card body */}
      <SkeletonText lines={3} />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// SkeletonTable – table-like skeleton with a header row + N body rows
// ─────────────────────────────────────────────────────────────────────────────

const COL_WIDTHS = ["w-1/4", "w-1/3", "w-1/5", "w-1/6", "w-1/4", "w-1/3"];

export function SkeletonTable({
  rows = 5,
  cols = 4,
}: {
  rows?: number;
  cols?: number;
}) {
  return (
    <div
      className="rounded-xl border border-[#2b3b55] bg-[#18202F] overflow-hidden"
      aria-hidden="true"
    >
      {/* Header row */}
      <div className="flex items-center gap-4 px-4 py-3 border-b border-[#2b3b55] bg-[#1e2a3d]">
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton
            key={i}
            className={cn(
              "h-3.5",
              COL_WIDTHS[i % COL_WIDTHS.length],
              "opacity-60"
            )}
          />
        ))}
      </div>

      {/* Body rows */}
      <div className="divide-y divide-[#1e2a3d]">
        {Array.from({ length: rows }).map((_, rowIdx) => (
          <div
            key={rowIdx}
            className="flex items-center gap-4 px-4 py-3"
          >
            {Array.from({ length: cols }).map((_, colIdx) => (
              <Skeleton
                key={colIdx}
                className={cn(
                  "h-4",
                  COL_WIDTHS[(rowIdx + colIdx) % COL_WIDTHS.length]
                )}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
