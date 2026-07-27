import { GenerationDashboard } from "./generation-dashboard";

export const dynamic = "force-dynamic";

export default function DashboardPage() {
  return <GenerationDashboard apiUrl={process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://localhost:7000"} />;
}
