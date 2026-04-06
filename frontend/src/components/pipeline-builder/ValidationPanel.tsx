'use client';

import { CheckCircle, XCircle, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';
import { cn } from '@/lib/utils';

interface ValidationPanelProps {
    errors: string[];
    isValid: boolean;
    isDirty: boolean;
}

export function ValidationPanel({ errors, isValid, isDirty }: ValidationPanelProps) {
    const [expanded, setExpanded] = useState(false);

    return (
        <div className="bg-zinc-900/90 backdrop-blur border border-zinc-700 rounded-xl shadow-xl overflow-hidden max-w-[320px]">
            <button
                onClick={() => setExpanded((v) => !v)}
                className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium"
            >
                {isValid ? (
                    <CheckCircle className="h-3.5 w-3.5 text-green-500 shrink-0" />
                ) : (
                    <XCircle className="h-3.5 w-3.5 text-red-500 shrink-0" />
                )}
                <span className={cn(isValid ? 'text-green-400' : 'text-red-400')}>
                    {isValid
                        ? isDirty
                            ? 'Valid (unsaved changes)'
                            : 'DAG Valid ✓'
                        : `${errors.length} validation error${errors.length !== 1 ? 's' : ''}`}
                </span>
                {!isValid && (
                    expanded
                        ? <ChevronDown className="h-3 w-3 text-zinc-500 ml-auto" />
                        : <ChevronUp className="h-3 w-3 text-zinc-500 ml-auto" />
                )}
            </button>

            {!isValid && expanded && (
                <div className="border-t border-zinc-700 px-3 py-2 space-y-1">
                    {errors.map((err, i) => (
                        <div key={i} className="flex items-start gap-1.5">
                            <AlertTriangle className="h-3 w-3 text-amber-500 shrink-0 mt-0.5" />
                            <span className="text-[11px] text-zinc-300">{err}</span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
