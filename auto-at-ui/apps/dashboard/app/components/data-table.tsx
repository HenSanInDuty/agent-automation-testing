import type { ReactNode } from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

export type DataColumn<T> = { key: string; header: string; render: (row: T) => ReactNode; className?: string };

export function DataTable<T extends { id: string }>({ columns, rows, empty, caption, className }: { columns: DataColumn<T>[]; rows: T[]; empty: ReactNode; caption?: string; className?: string }) {
  if (rows.length === 0) return <>{empty}</>;
  return <div className={cn("overflow-hidden rounded-xl border bg-card shadow-xs", className)}>
    <Table>
      {caption && <caption className="sr-only">{caption}</caption>}
      <TableHeader className="bg-muted/50">
        <TableRow className="hover:bg-transparent">{columns.map((column) => <TableHead key={column.key} scope="col" className={cn("h-10 px-4 text-xs font-medium uppercase tracking-wide text-muted-foreground", column.className)}>{column.header}</TableHead>)}</TableRow>
      </TableHeader>
      <TableBody>{rows.map((row) => <TableRow key={row.id}>{columns.map((column) => <TableCell key={column.key} className={cn("px-4 py-3", column.className)}>{column.render(row)}</TableCell>)}</TableRow>)}</TableBody>
    </Table>
  </div>;
}
