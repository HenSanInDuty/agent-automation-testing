"use client";
import { PlayCircle } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader } from "../components/page-header";
import { EmptyState } from "../components/states";
import { StatusBadge } from "../components/status-badge";
import { runs, type Run } from "../run-api";

const statuses = ["queued", "running", "passed", "failed", "errored", "cancelled"];

export default function RunsPage() {
  const apiUrl = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "";
  const [items, setItems] = useState<Run[]>([]);
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const selectId = useId();

  useEffect(() => {
    let disposed = false;
    runs(apiUrl, status ? `status=${encodeURIComponent(status)}` : "")
      .then((page) => { if (!disposed) setItems(page.items); })
      .catch(() => { if (!disposed) setItems([]); })
      .finally(() => { if (!disposed) setLoading(false); });
    return () => { disposed = true; };
  }, [apiUrl, status]);

  return (
    <>
      <PageHeader eyebrow="Execution" title="Runs" description="Find and investigate deterministic test executions." />
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Label htmlFor={selectId} className="text-sm text-muted-foreground">Status</Label>
          <NativeSelect id={selectId} value={status} onChange={(event) => setStatus(event.target.value)}>
            <NativeSelectOption value="">All statuses</NativeSelectOption>
            {statuses.map((value) => <NativeSelectOption key={value} value={value}>{value}</NativeSelectOption>)}
          </NativeSelect>
        </div>
        <p className="text-sm text-muted-foreground" aria-live="polite">
          {loading ? "Loading runs..." : `${items.length} ${items.length === 1 ? "run" : "runs"}`}
        </p>
      </div>
      {loading ? (
        <Card className="overflow-hidden py-0" aria-busy="true" aria-label="Loading runs">
          <div className="space-y-3 p-4">
            {Array.from({ length: 5 }, (_, index) => <Skeleton key={index} className="h-9 w-full" />)}
          </div>
        </Card>
      ) : items.length ? (
        <Card className="overflow-hidden py-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Run</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Test</TableHead>
                <TableHead className="pr-4">Revision</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item) => (
                <TableRow key={item.id} className="hover:bg-muted/50">
                  <TableCell className="pl-4">
                    <Link
                      href={`/runs/${item.id}`}
                      title={item.id}
                      className="block max-w-32 truncate font-mono text-xs font-medium text-primary underline-offset-4 hover:underline"
                    >
                      {item.id.slice(0, 8)}
                    </Link>
                  </TableCell>
                  <TableCell><StatusBadge status={item.status} /></TableCell>
                  <TableCell className="max-w-72 truncate" title={item.test_case_name ?? item.test_case_id}>
                    {item.test_case_name ?? item.test_case_id}
                  </TableCell>
                  <TableCell className="pr-4">
                    <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs" title={item.revision}>
                      {item.revision.slice(0, 12)}
                    </code>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      ) : (
        <EmptyState
          title="No runs match the current filter."
          icon={<PlayCircle />}
          action={<Button asChild variant="outline"><Link href="/projects">Go to projects</Link></Button>}
        >
          Start a run from a project test case, or clear the status filter.
        </EmptyState>
      )}
    </>
  );
}
