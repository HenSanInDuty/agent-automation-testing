'use client';

import { Handle, Position } from '@xyflow/react';
import type { NodeProps } from '@xyflow/react';

export function InputNode({ selected }: NodeProps) {
    return (
        <div
            className={`
                px-4 py-3 rounded-xl border-2 bg-blue-950 border-blue-600 shadow-lg
                min-w-[140px] transition-all
                ${selected ? 'ring-2 ring-blue-400' : ''}
            `}
        >
            <div className="flex items-center gap-2">
                <span className="text-lg">📥</span>
                <div>
                    <div className="font-semibold text-sm text-blue-200">Input</div>
                    <div className="text-xs text-blue-400">Pipeline Entry</div>
                </div>
            </div>
            {/* Only source handle */}
            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-3 !h-3 !bg-blue-500 !border-2 !border-blue-950"
            />
        </div>
    );
}
