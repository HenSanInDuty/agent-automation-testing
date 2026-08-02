import { PageHeader } from "../components/page-header";
import { EmptyState } from "../components/states";

export default function ReviewsPage() {
  return <><PageHeader eyebrow="Governance" title="Reviews" description="Review evidence-backed agent proposals and immutable decisions." /><EmptyState title="Review queue is coming next">The governed generation workflow remains available in Agent workspace while the shared review queue is introduced in M5.</EmptyState></>;
}
