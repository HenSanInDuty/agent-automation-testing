import type { Metadata } from 'next';
import { PipelineBuilder } from '@/components/pipeline-builder/PipelineBuilder';

interface Props {
    params: Promise<{ templateId: string }>;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
    const { templateId } = await params;
    return {
        title: `Edit Pipeline – ${templateId}`,
        description: 'Visual pipeline builder',
    };
}

export default async function PipelineBuilderPage({ params }: Props) {
    const { templateId } = await params;
    return (
        <div className="h-[calc(100dvh-3.5rem)] -mx-4 sm:-mx-6 -my-6">
            <PipelineBuilder templateId={templateId} />
        </div>
    );
}
