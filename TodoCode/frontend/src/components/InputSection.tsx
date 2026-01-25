'use client';

import { useState } from 'react';

interface Props {
    onAddTask: (title: string, start: string, end: string) => void;
}

export default function InputSection({ onAddTask }: Props) {
    const [title, setTitle] = useState('');
    const [start, setStart] = useState('');
    const [end, setEnd] = useState('');

    const handleSubmit = () => {
        if (!title.trim()) return;
        onAddTask(title, start, end);
        setTitle('');
        setStart('');
        setEnd('');
    };

    return (
        <div className="w-full max-w-2xl relative group">
            <div className="flex flex-col w-full shadow-2xl shadow-primary/5 bg-[#1c2636] rounded-xl border border-border-dark focus-within:border-primary focus-within:ring-1 focus-within:ring-primary transition-all duration-200">
                <div className="flex w-full items-center p-2">
                    <input
                        className="flex-1 bg-transparent text-white placeholder:text-[#5a6b8c] px-4 text-lg font-medium outline-none"
                        placeholder="What needs to be done today?"
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
                    />
                    <div className="flex items-center gap-2 pr-2">
                        <input
                            type="time"
                            className="bg-[#2b3b55] text-white rounded px-2 py-1 text-sm outline-none border border-transparent focus:border-primary"
                            value={start}
                            onChange={(e) => setStart(e.target.value)}
                        />
                        <span className="text-[#5a6b8c]">-</span>
                        <input
                            type="time"
                            className="bg-[#2b3b55] text-white rounded px-2 py-1 text-sm outline-none border border-transparent focus:border-primary"
                            value={end}
                            onChange={(e) => setEnd(e.target.value)}
                        />
                        <button
                            onClick={handleSubmit}
                            className="flex items-center justify-center rounded-lg h-10 w-10 bg-primary hover:bg-blue-600 text-white transition-colors duration-200 ml-2"
                        >
                            <span className="material-symbols-outlined text-2xl">add</span>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
