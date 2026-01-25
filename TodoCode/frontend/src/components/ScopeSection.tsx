'use client';

import { useState } from 'react';
import { Goal } from '@/types';

interface Props {
    goals: Goal[];
    onAddGoal: (title: string, type: 'day' | 'month' | 'year') => void;
    onDeleteGoal: (id: number) => void;
    selectedDate: string;
}

export default function ScopeSection({ goals, onAddGoal, onDeleteGoal, selectedDate }: Props) {
    const [activeTab, setActiveTab] = useState<'day' | 'month' | 'year'>('day');
    const [isAdding, setIsAdding] = useState(false);
    const [newGoal, setNewGoal] = useState('');
    const [expandedGoalId, setExpandedGoalId] = useState<number | null>(null);

    const filteredGoals = goals.filter(g => g.type === activeTab);

    const handleAdd = () => {
        if (newGoal.trim()) {
            onAddGoal(newGoal, activeTab);
            setNewGoal('');
            setIsAdding(false);
        }
    };

    return (
        <aside className="lg:col-span-3 flex flex-col gap-6">
            <div className="flex items-center gap-2 pb-2 border-b border-border-dark">
                <span className="material-symbols-outlined text-[#92a4c9]">rocket_launch</span>
                <h2 className="text-[#92a4c9] text-sm font-bold uppercase tracking-wider">Scope</h2>
            </div>

            <div className="flex p-1 bg-[#1c2636] rounded-lg border border-border-dark">
                {(['day', 'month', 'year'] as const).map(tab => (
                    <button
                        key={tab}
                        onClick={() => {
                            setActiveTab(tab);
                            setExpandedGoalId(null);
                        }}
                        className={`flex-1 py-2 rounded-md text-sm font-medium transition-all capitalize ${activeTab === tab
                            ? 'bg-primary text-white shadow-sm font-semibold'
                            : 'text-[#92a4c9] hover:bg-white/5'
                            }`}
                    >
                        {tab}
                    </button>
                ))}
            </div>

            <div className="flex flex-col gap-3">
                {filteredGoals.map(goal => {
                    const isExpanded = expandedGoalId === goal.id;
                    return (
                        <div
                            key={goal.id}
                            onClick={() => setExpandedGoalId(isExpanded ? null : goal.id)}
                            className={`p-4 rounded-xl bg-[#1c2636] border border-border-dark/50 hover:border-primary/50 transition-all group cursor-pointer flex justify-between items-start ${isExpanded ? 'ring-2 ring-primary/20 bg-[#243042]' : ''}`}
                        >
                            <div className="flex-1 min-w-0">
                                <h3 className={`text-white font-semibold mb-1 transition-all ${isExpanded ? '' : 'truncate'}`}>
                                    {goal.title}
                                </h3>
                                <p className="text-[#92a4c9] text-xs">Goal for {goal.type}</p>
                            </div>
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    onDeleteGoal(goal.id);
                                }}
                                className="opacity-0 group-hover:opacity-100 p-1 hover:bg-red-500/20 rounded-lg text-[#92a4c9] hover:text-red-500 transition-all shrink-0 ml-2"
                            >
                                <span className="material-symbols-outlined text-[18px]">delete</span>
                            </button>
                        </div>
                    );
                })}

                {isAdding ? (
                    <div className="p-4 rounded-xl bg-[#1c2636] border border-border-dark flex flex-col gap-2">
                        <input
                            autoFocus
                            className="bg-transparent text-white outline-none placeholder:text-gray-500 text-sm"
                            placeholder="New goal..."
                            value={newGoal}
                            onChange={(e) => setNewGoal(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
                            onBlur={() => !newGoal && setIsAdding(false)}
                        />
                        <button onClick={handleAdd} className="text-xs text-primary self-end">Add</button>
                    </div>
                ) : (
                    <div
                        onClick={() => setIsAdding(true)}
                        className="p-4 rounded-xl border border-dashed border-border-dark flex items-center justify-center gap-2 text-[#92a4c9] hover:text-white hover:border-primary/50 hover:bg-primary/5 cursor-pointer transition-all py-6"
                    >
                        <span className="material-symbols-outlined text-[20px]">add_circle</span>
                        <span className="text-sm font-medium">Add Goal</span>
                    </div>
                )}
            </div>
        </aside>
    );
}
