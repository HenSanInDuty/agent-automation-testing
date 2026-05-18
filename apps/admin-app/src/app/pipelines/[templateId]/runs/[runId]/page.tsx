import type { Metadata } from 'next';
import { PipelineRunDetailPage } from '@/components/pipeline/PipelineRunDetailPage';

interface Props {
  params: Promise<{ templateId: string; runId: string }>;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { templateId, runId } = await params;
  return {
    title: `Run ${runId.slice(0, 8)} – ${templateId}`,
    description: 'Pipeline run detail',
  };
}

export default async function PipelineRunDetailRoutePage({ params }: Props) {
  const { templateId, runId } = await params;
  return (
    <div className="flex flex-col gap-6">
      <PipelineRunDetailPage templateId={templateId} runId={runId} />
    </div>
  );
}
