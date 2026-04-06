'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft, GitBranch, Plus } from 'lucide-react';
import Link from 'next/link';
import { useCreateTemplate } from '@/hooks/usePipelineTemplates';
import { cn } from '@/lib/utils';

export default function NewPipelinePage() {
    const router = useRouter();
    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [templateId, setTemplateId] = useState('');
    const [error, setError] = useState('');

    const createTemplate = useCreateTemplate();

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');

        if (!name.trim()) {
            setError('Pipeline name is required');
            return;
        }
        if (!templateId.trim()) {
            setError('Template ID is required');
            return;
        }
        // Validate template_id format (lowercase, alphanumeric + underscore/hyphen)
        if (!/^[a-z0-9_-]+$/.test(templateId.trim())) {
            setError('Template ID can only contain lowercase letters, numbers, underscores, and hyphens');
            return;
        }

        try {
            const template = await createTemplate.mutateAsync({
                template_id: templateId.trim(),
                name: name.trim(),
                description: description.trim(),
                nodes: [],
                edges: [],
                tags: [],
            });
            router.push(`/pipelines/${template.template_id}`);
        } catch (err: unknown) {
            const message = err instanceof Error ? err.message : 'Failed to create pipeline';
            setError(message);
        }
    };

    const suggestTemplateId = (pipelineName: string) => {
        return pipelineName
            .toLowerCase()
            .replace(/\s+/g, '_')
            .replace(/[^a-z0-9_-]/g, '')
            .slice(0, 40);
    };

    return (
        <div className="max-w-lg mx-auto py-10 px-4">
            {/* Back link */}
            <Link
                href="/pipelines"
                className="inline-flex items-center gap-1.5 text-sm text-[#92a4c9] hover:text-white mb-6 transition-colors"
            >
                <ArrowLeft className="w-4 h-4" />
                Back to Pipelines
            </Link>

            {/* Header */}
            <div className="flex items-center gap-3 mb-8">
                <div className="w-10 h-10 rounded-xl bg-[#1e2a3d] border border-[#2b3b55] flex items-center justify-center">
                    <GitBranch className="w-5 h-5 text-[#5b9eff]" />
                </div>
                <div>
                    <h1 className="text-xl font-bold text-white">New Pipeline</h1>
                    <p className="text-sm text-[#92a4c9]">Create a new pipeline template</p>
                </div>
            </div>

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-5">
                {/* Name */}
                <div className="space-y-1.5">
                    <label className="text-sm font-medium text-[#92a4c9]">
                        Pipeline Name <span className="text-red-400">*</span>
                    </label>
                    <input
                        type="text"
                        value={name}
                        onChange={(e) => {
                            setName(e.target.value);
                            // Auto-suggest template_id if not manually edited
                            if (!templateId || templateId === suggestTemplateId(name)) {
                                setTemplateId(suggestTemplateId(e.target.value));
                            }
                        }}
                        placeholder="e.g. Auto Testing Pipeline"
                        className={cn(
                            'w-full h-10 px-3 rounded-lg text-sm',
                            'bg-[#1e2a3d] border border-[#2b3b55]',
                            'text-white placeholder-[#3d5070]',
                            'focus:outline-none focus:ring-2 focus:ring-[#135bec]/50 focus:border-[#135bec]',
                        )}
                    />
                </div>

                {/* Template ID */}
                <div className="space-y-1.5">
                    <label className="text-sm font-medium text-[#92a4c9]">
                        Template ID <span className="text-red-400">*</span>
                    </label>
                    <input
                        type="text"
                        value={templateId}
                        onChange={(e) => setTemplateId(e.target.value)}
                        placeholder="e.g. auto_testing_pipeline"
                        className={cn(
                            'w-full h-10 px-3 rounded-lg text-sm font-mono',
                            'bg-[#1e2a3d] border border-[#2b3b55]',
                            'text-white placeholder-[#3d5070]',
                            'focus:outline-none focus:ring-2 focus:ring-[#135bec]/50 focus:border-[#135bec]',
                        )}
                    />
                    <p className="text-xs text-[#3d5070]">
                        Unique identifier — lowercase, letters, numbers, underscores, hyphens only
                    </p>
                </div>

                {/* Description */}
                <div className="space-y-1.5">
                    <label className="text-sm font-medium text-[#92a4c9]">Description</label>
                    <textarea
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        placeholder="Describe what this pipeline does..."
                        rows={3}
                        className={cn(
                            'w-full px-3 py-2 rounded-lg text-sm resize-none',
                            'bg-[#1e2a3d] border border-[#2b3b55]',
                            'text-white placeholder-[#3d5070]',
                            'focus:outline-none focus:ring-2 focus:ring-[#135bec]/50 focus:border-[#135bec]',
                        )}
                    />
                </div>

                {/* Error */}
                {error && (
                    <div className="px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-400">
                        {error}
                    </div>
                )}

                {/* Submit */}
                <div className="flex gap-3 pt-2">
                    <Link
                        href="/pipelines"
                        className={cn(
                            'flex-1 h-10 flex items-center justify-center rounded-lg text-sm',
                            'border border-[#2b3b55] text-[#92a4c9] hover:text-white hover:bg-[#1e2a3d]',
                            'transition-colors',
                        )}
                    >
                        Cancel
                    </Link>
                    <button
                        type="submit"
                        disabled={createTemplate.isPending}
                        className={cn(
                            'flex-1 h-10 flex items-center justify-center gap-2 rounded-lg text-sm font-medium',
                            'bg-[#135bec] text-white hover:bg-[#1a6aff]',
                            'transition-colors',
                            'disabled:opacity-50 disabled:cursor-not-allowed',
                        )}
                    >
                        <Plus className="w-4 h-4" />
                        {createTemplate.isPending ? 'Creating...' : 'Create Pipeline'}
                    </button>
                </div>
            </form>
        </div>
    );
}
