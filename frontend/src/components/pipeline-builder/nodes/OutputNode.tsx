'use client';

import { Handle, Position } from '@xyflow/react';
import type { NodeProps } from '@xyflow/react';

export function OutputNode({ selected }: NodeProps) {
    return (
        <div
            className={`
                px-4 py-3 rounded-xl border-2 bg-green-950 border-green-600 shadow-lg
                min-w-[140px] transition-all
                ${selected ? 'ring-2 ring-blue-400' : ''}
            `}
        >
            {/* Only target handle */}
            <Handle
                type="target"
                position={Position.Top}
                className="!w-3 !h-3 !bg-green-500 !border-2 !border-green-950"
            />
            <div className="flex items-center gap-2">
                <span className="text-lg">📤</span>
                <div>
                    <div className="font-semibold text-sm text-green-200">Output</div>
                    <div className="text-xs text-green-400">Pipeline Exit</div>
                </div>
            </div>
        </div>
    );
}
