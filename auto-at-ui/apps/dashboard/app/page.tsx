type DashboardSection = {
  title: string;
  description: string;
  endpoint: string;
  count: number | null;
};

export const dynamic = "force-dynamic";

type OperationsSummary = {
  projects: number;
  tests: number;
  runs: number;
  artifacts: number;
  proposals: number;
  approvals: number;
  audit_events: number;
};

async function loadSummary(): Promise<OperationsSummary | null> {
  const apiUrl = process.env.CONTROL_PLANE_URL;
  const tenantId = process.env.DASHBOARD_TENANT_ID;
  if (!apiUrl || !tenantId) return null;

  const response = await fetch(`${apiUrl}/api/v1/operations/summary`, {
    headers: { "X-Tenant-Id": tenantId },
    cache: "no-store",
  });
  return response.ok ? (response.json() as Promise<OperationsSummary>) : null;
}

export default async function DashboardPage() {
  const summary = await loadSummary();
  const sections: DashboardSection[] = [
    { title: "Projects", description: "Authorized project catalogue", endpoint: "/projects", count: summary?.projects ?? null },
    { title: "Tests", description: "Versioned test definitions", endpoint: "/tests", count: summary?.tests ?? null },
    { title: "Runs", description: "Correlated deterministic execution history", endpoint: "/runs", count: summary?.runs ?? null },
    { title: "Artifacts", description: "Checksum-verified run evidence", endpoint: "/runs/{runId}/artifacts", count: summary?.artifacts ?? null },
    { title: "Proposals", description: "Redacted AI proposals awaiting review", endpoint: "/proposals/{proposalId}", count: summary?.proposals ?? null },
    { title: "Approvals", description: "Human decisions and reasons", endpoint: "/proposals/{proposalId}/decision", count: summary?.approvals ?? null },
    { title: "Audit history", description: "Append-only correlated actions", endpoint: "/audit-events", count: summary?.audit_events ?? null },
  ];
  return (
    <main>
      <h1>Auto-AT Operations</h1>
      <p>All data is read and changed through the authorized control-plane API.</p>
      <section aria-label="Operational views">
        {sections.map((section) => (
          <article key={section.title}>
            <h2>{section.title}</h2>
            <p>{section.description}</p>
            <p>{section.count === null ? "Configure dashboard API access" : `${section.count} records`}</p>
            <code>API {section.endpoint}</code>
          </article>
        ))}
      </section>
    </main>
  );
}
