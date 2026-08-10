import { PageHeader } from "../components/page-header";
import { ReviewsDashboard } from "./reviews-dashboard";

export default function ReviewsPage() {
  const apiUrl = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://localhost:7000";
  return <><PageHeader eyebrow="Governance" title="Reviews" description="Review evidence-backed agent proposals and immutable decisions." /><ReviewsDashboard apiUrl={apiUrl} /></>;
}
