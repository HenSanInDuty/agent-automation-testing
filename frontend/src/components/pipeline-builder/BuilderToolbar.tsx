'use client';

import { Save, Play, Undo2, Redo2, RotateCcw, CheckCircle, XCircle } from 'lucide-react';
import { useBuilderStore } from '@/store/builderStore';
import { cn } from '@/lib/utils';

interface BuilderToolbarProps {
    onSave?: () => Promise<void>;
    onRun?: () => void;
    templateId?: string | null;
}

export function BuilderToolbar({ onSave, onRun, templateId }: BuilderToolbarProps) {
    const {
        isDirty,
        isSaving,
        isValid,
        validationErrors,
        undo,
        redo,
        history,
        historyIndex,
        validate,
        templateName,
    } = useBuilderStore();

    const canUndo = historyIndex > 0;
    const canRedo = historyIndex < history.length - 1;

    return (
        <div className="flex items-center gap-2 bg-zinc-900/90 backdrop-blur border border-zinc-700 rounded-xl px-3 py-2 shadow-xl">
            {/* Template name */}
            {templateName && (
                <span className="text-xs text-zinc-400 mr-1 max-w-[120px] truncate">
                    {templateName}
                </span>
            )}

            {/* Divider */}
            {templateName && <div className="w-px h-4 bg-zinc-700" />}

            {/* Undo */}
            <button
                onClick={undo}
                disabled={!canUndo}
                title="Undo"
                className={cn(
                    'p-1.5 rounded-lg transition-colors',
                    canUndo
                        ? 'text-zinc-300 hover:bg-zinc-700 hover:text-white'
                        : 'text-zinc-600 cursor-not-allowed',
                )}
            >
                <Undo2 className="h-4 w-4" />
            </button>

            {/* Redo */}
            <button
                onClick={redo}
                disabled={!canRedo}
                title="Redo"
                className={cn(
                    'p-1.5 rounded-lg transition-colors',
                    canRedo
                        ? 'text-zinc-300 hover:bg-zinc-700 hover:text-white'
                        : 'text-zinc-600 cursor-not-allowed',
                )}
            >
                <Redo2 className="h-4 w-4" />
            </button>

            {/* Validate */}
            <button
                onClick={() => validate()}
                title="Validate DAG"
                className="p-1.5 rounded-lg text-zinc-300 hover:bg-zinc-700 hover:text-white transition-colors"
            >
                <RotateCcw className="h-4 w-4" />
            </button>

            {/* Validation indicator */}
            <div title={validationErrors.join('\n')} className="flex items-center">
                {isValid ? (
                    <CheckCircle className="h-4 w-4 text-green-500" />
                ) : (
                    <XCircle className="h-4 w-4 text-red-500" />
                )}
            </div>

            <div className="w-px h-4 bg-zinc-700" />

            {/* Save */}
            <button
                onClick={onSave}
                disabled={!isDirty || isSaving}
                title="Save"
                className={cn(
                    'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                    isDirty && !isSaving
                        ? 'bg-[#135bec] text-white hover:bg-[#1a6aff]'
                        : 'bg-zinc-800 text-zinc-500 cursor-not-allowed',
                )}
            >
                <Save className="h-3.5 w-3.5" />
                {isSaving ? 'Saving...' : 'Save'}
            </button>

            {/* Run */}
            {onRun && (
                <button
                    onClick={onRun}
                    disabled={!isValid}
                    title={isValid ? 'Run Pipeline' : 'Fix validation errors first'}
                    className={cn(
                        'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                        isValid
                            ? 'bg-green-700 text-white hover:bg-green-600'
                            : 'bg-zinc-800 text-zinc-500 cursor-not-allowed',
                    )}
                >
                    <Play className="h-3.5 w-3.5" />
                    Run
                </button>
            )}
        </div>
    );
}
