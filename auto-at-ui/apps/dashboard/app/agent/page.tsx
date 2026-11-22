import { GenerationDashboard } from "../generation-dashboard";
import "../vision.css";

export const dynamic = "force-dynamic";

export default function AgentWorkspacePage() {
  return <GenerationDashboard apiUrl={process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? ""} />;
}
