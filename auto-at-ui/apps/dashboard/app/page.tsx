import { PageHeader } from "./components/page-header";
import { EmptyState } from "./components/states";

export const dynamic = "force-dynamic";

export default function DashboardPage() {
  return <><PageHeader eyebrow="Demo tenant" title="Overview" description="A clear starting point for test operations. Live portfolio summaries arrive with the catalog and run APIs in M3." /><EmptyState title="Your operational overview is coming next">Create and investigate deterministic runs from the dashboard once Projects & Tests is connected.</EmptyState></>;
}
