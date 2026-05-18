'use client';

import { CheckCircle, XCircle, AlertTriangle, Info, ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';
import { cn } from '@/lib/utils';

interface ValidationPanelProps {
    errors: string[];
    warnings?: string[];
    isValid: boolean;
    isDirty: boolean;
}

export function ValidationPanel({ errors, warnings = [], isValid, isDirty }: ValidationPanelProps) {
    const [expanded, setExpanded] = useState(false);
    const hasWarnings = warnings.length > 0;
    const hasIssues = !isValid || hasWarnings;

    return (
        <div className="bg-zinc-900/90 backdrop-blur border border-zinc-700 rounded-xl shadow-xl overflow-hidden max-w-[340px]">
            <button
                onClick={() => setExpanded((v) => !v)}
                className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium"
            >
                {isValid ? (
                    hasWarnings ? (
                        <AlertTriangle className="h-3.5 w-3.5 text-amber-400 shrink-0" />
                    ) : (
                        <CheckCircle className="h-3.5 w-3.5 text-green-500 shrink-0" />
                    )
                ) : (
                    <XCircle className="h-3.5 w-3.5 text-red-500 shrink-0" />
                )}
                <span className={cn(
                    isValid
                        ? hasWarnings ? 'text-amber-400' : 'text-green-400'
                        : 'text-red-400'
                )}>
                    {!isValid
                        ? `${errors.length} error${errors.length !== 1 ? 's' : ''}`
                        : hasWarnings
                            ? `${warnings.length} warning${warnings.length !== 1 ? 's' : ''}`
                            : isDirty
                                ? 'Valid (unsaved changes)'
                                : 'DAG Valid ✓'}
                </span>
                {hasIssues && (
                    expanded
                        ? <ChevronDown className="h-3 w-3 text-zinc-500 ml-auto" />
                        : <ChevronUp className="h-3 w-3 text-zinc-500 ml-auto" />
                )}
            </button>

            {hasIssues && expanded && (
                <div className="border-t border-zinc-700 px-3 py-2 space-y-1.5">
                    {errors.map((err, i) => (
                        <div key={`e-${i}`} className="flex items-start gap-1.5">
                            <XCircle className="h-3 w-3 text-red-500 shrink-0 mt-0.5" />
                            <span className="text-[11px] text-zinc-300">{err}</span>
                        </div>
                    ))}
                    {errors.length > 0 && warnings.length > 0 && (
                        <div className="border-t border-zinc-800 my-1" />
                    )}
                    {warnings.map((w, i) => (
                        <div key={`w-${i}`} className="flex items-start gap-1.5">
                            <Info className="h-3 w-3 text-amber-400 shrink-0 mt-0.5" />
                            <span className="text-[11px] text-zinc-400">{w}</span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
