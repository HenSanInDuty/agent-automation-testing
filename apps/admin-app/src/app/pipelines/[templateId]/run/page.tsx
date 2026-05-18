import type { Metadata } from 'next';
import { PipelineRunPage } from '@/components/pipeline/PipelineRunPage';

interface Props {
  params: Promise<{ templateId: string }>;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { templateId } = await params;
  return {
    title: `Run Pipeline – ${templateId}`,
    description: 'Run pipeline with live DAG visualization',
  };
}

export default async function PipelineRunRoutePage({ params }: Props) {
  const { templateId } = await params;
  return (
    <div className="flex flex-col gap-6">
      <PipelineRunPage templateId={templateId} />
    </div>
  );
}
