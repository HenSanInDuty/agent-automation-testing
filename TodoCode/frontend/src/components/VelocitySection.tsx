'use client';

import { Stats } from '@/types';

interface Props {
    stats: Stats;
}

export default function VelocitySection({ stats }: Props) {
    const percentage = Math.round(stats.daily_goal);
    // Simple bar chart scaling
    const maxRate = 100;

    return (
        <div className="flex flex-col gap-4">
            <div className="flex items-center gap-2 pb-2 border-b border-border-dark">
                <span className="material-symbols-outlined text-[#92a4c9]">monitoring</span>
                <h2 className="text-[#92a4c9] text-sm font-bold uppercase tracking-wider">Velocity</h2>
            </div>
            <div className="grid grid-cols-2 gap-4">
                {/* Progress Ring */}
                <div className="bg-[#1c2636] rounded-xl p-4 border border-border-dark flex flex-col items-center justify-center gap-3">
                    <div className="relative size-20">
                        <svg className="size-full -rotate-90" viewBox="0 0 36 36" xmlns="http://www.w3.org/2000/svg">
                            <path className="text-[#2b3b55]" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="currentColor" strokeWidth="4"></path>
                            <path className="text-primary transition-all duration-1000 ease-out" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="currentColor" strokeDasharray={`${percentage}, 100`} strokeLinecap="round" strokeWidth="4"></path>
                        </svg>
                        <div className="absolute top-1/2 left-1/2 -translate-y-1/2 -translate-x-1/2 text-center">
                            <span className="text-sm font-bold text-white">{percentage}%</span>
                        </div>
                    </div>
                    <span className="text-xs text-[#92a4c9] font-medium">Daily Goal</span>
                </div>

                {/* Bar Chart */}
                <div className="bg-[#1c2636] rounded-xl p-4 border border-border-dark flex flex-col justify-end">
                    <div className="flex items-end justify-between h-20 gap-1.5">
                        {stats.last_5_days.map((day, i) => (
                            <div
                                key={day.date}
                                className={`w-full rounded-t-sm transition-colors ${i === 4 ? 'bg-primary' : 'bg-[#2b3b55] hover:bg-primary/50'}`}
                                style={{ height: `${Math.max(day.rate, 10)}%` }} // min height for visibility
                                title={`${day.date}: ${day.rate.toFixed(0)}%`}
                            ></div>
                        ))}
                    </div>
                    <div className="border-t border-border-dark mt-2 pt-2 text-center">
                        <span className="text-xs text-[#92a4c9] font-medium">Last 5 Days</span>
                    </div>
                </div>
            </div>
        </div>
    );
}
