import { RunComparePage } from "@auto-at/shared/components/pipeline/RunComparePage";

interface Props {
  params: Promise<{ templateId: string }>;
  searchParams: Promise<{ runs?: string; nodes?: string }>;
}

export default async function Page({ params, searchParams }: Props) {
  const { templateId } = await params;
  const query = await searchParams;
  const runIds = query.runs ? query.runs.split(",").filter(Boolean) : [];
  const nodeIds = query.nodes ? query.nodes.split(",").filter(Boolean) : [];

  return (
    <RunComparePage
      templateId={templateId}
      runIds={runIds}
      nodeIds={nodeIds}
    />
  );
}
