import type { Metadata } from 'next';
import { PipelineRunHistoryPage } from '@/components/pipeline/PipelineRunHistoryPage';

interface Props {
  params: Promise<{ templateId: string }>;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { templateId } = await params;
  return {
    title: `Run History – ${templateId}`,
    description: 'Pipeline run history',
  };
}

export default async function PipelineRunHistoryRoutePage({ params }: Props) {
  const { templateId } = await params;
  return (
    <div className="flex flex-col gap-6">
      <PipelineRunHistoryPage templateId={templateId} />
    </div>
  );
}
