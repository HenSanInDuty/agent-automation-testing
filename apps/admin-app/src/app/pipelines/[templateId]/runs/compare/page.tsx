import { RunComparePage } from "@auto-at/shared/components/pipeline/RunComparePage";

interface Props {
  params: { templateId: string };
  searchParams: { runs?: string; nodes?: string };
}

export default function Page({ params, searchParams }: Props) {
  const runIds = searchParams.runs ? searchParams.runs.split(",").filter(Boolean) : [];
  const nodeIds = searchParams.nodes ? searchParams.nodes.split(",").filter(Boolean) : [];

  return (
    <RunComparePage
      templateId={params.templateId}
      runIds={runIds}
      nodeIds={nodeIds}
    />
  );
}
