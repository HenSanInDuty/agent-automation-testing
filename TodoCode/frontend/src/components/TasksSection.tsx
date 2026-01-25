'use client';

import { Task } from '@/types';

interface Props {
    tasks: Task[];
    onToggle: (id: number, isDone: boolean) => void;
    onDelete: (id: number) => void;
}

export default function TasksSection({ tasks, onToggle, onDelete }: Props) {
    const remaining = tasks.filter(t => !t.is_done).length;

    return (
        <section className="lg:col-span-6 flex flex-col gap-6">
            <div className="flex items-center justify-between pb-2 border-b border-border-dark">
                <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined text-[#92a4c9]">check_circle</span>
                    <h2 className="text-[#92a4c9] text-sm font-bold uppercase tracking-wider">Current Tasks</h2>
                </div>
                <span className="text-xs font-medium text-primary bg-primary/10 px-2 py-1 rounded-full">{remaining} Remaining</span>
            </div>

            <div className="flex flex-col gap-1">
                {tasks.map(task => (
                    <div key={task.id} className={`group flex items-center gap-4 px-4 py-4 rounded-xl transition-all duration-200 ${task.is_done ? 'bg-[#1c2636]/50 opacity-60 hover:opacity-100' : 'bg-[#1c2636] hover:bg-[#232f42] border border-transparent hover:border-border-dark'}`}>
                        <div className="flex size-6 items-center justify-center shrink-0">
                            <input
                                checked={task.is_done}
                                onChange={(e) => onToggle(task.id, e.target.checked)}
                                className="h-5 w-5 rounded border-[#5a6b8c] border-2 bg-transparent text-primary checked:bg-primary checked:border-primary focus:ring-0 focus:ring-offset-0 focus:outline-none transition-colors cursor-pointer"
                                type="checkbox"
                            />
                        </div>
                        <div className="flex flex-col flex-1 min-w-0">
                            <p className={`text-white text-base font-medium leading-normal truncate ${task.is_done ? 'line-through decoration-slate-500' : ''}`}>{task.title}</p>
                            {task.start_time && (
                                <span className="text-xs text-[#92a4c9] flex items-center gap-1 mt-0.5">
                                    <span className="material-symbols-outlined text-[12px]">schedule</span>
                                    {task.start_time} - {task.end_time}
                                </span>
                            )}
                        </div>
                        <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                            <button onClick={() => onDelete(task.id)} className="p-2 hover:bg-red-500/20 rounded-lg text-[#92a4c9] hover:text-red-500 transition-colors">
                                <span className="material-symbols-outlined text-[20px]">delete</span>
                            </button>
                        </div>
                    </div>
                ))}
            </div>
        </section>
    );
}
