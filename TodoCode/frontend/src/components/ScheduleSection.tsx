'use client';

import React, { useState, useMemo } from 'react';
import { Task } from '@/types';

interface Props {
    tasks: Task[];
    selectedDate: string;
    onSelectDate: (date: string) => void;
    successDays: string[];
}

export default function ScheduleSection({ tasks, selectedDate, onSelectDate, successDays }: Props) {
    // viewDate tracks which month is currently visible in the calendar
    const [viewDate, setViewDate] = useState(new Date());
    const dateInputRef = React.useRef<HTMLInputElement>(null);
    const monthInputRef = React.useRef<HTMLInputElement>(null);

    // Use selected date for the calendar view if we want to navigate months? 
    // For now, simpler: always show CURRENT MONTH, but allow selecting days within it.
    // If selectedDate is not in current month, we might want to shift view.
    // But let's keep it simple: Calendar shows Current Month.

    const currentDay = new Date().getDate();
    const isCurrentMonth = viewDate.getMonth() === new Date().getMonth() && viewDate.getFullYear() === new Date().getFullYear();

    const viewMonth = viewDate.getMonth();
    const viewYear = viewDate.getFullYear();
    const monthName = viewDate.toLocaleString('default', { month: 'long' });

    const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
    // Start day of week (0 = Sunday)
    const startDay = new Date(viewYear, viewMonth, 1).getDay();

    // Calculate status for today
    const todaysTasks = tasks.filter(t => !t.is_done); // Simplification: assuming input tasks are for today or filtration happens upstream
    // Actually we need ALL tasks for today to calc percentage
    // Let's assume the passed `tasks` prop contains tasks for the CURRENT VIEW (which is today).
    // So we can just use that.

    // But wait, the component might receive *all* tasks if we aren't filtering.
    // Let's assume parent filters for now or we just use what we have.
    // If we want to show green/red button, we need percentage.

    const total = tasks.length;
    const done = tasks.filter(t => t.is_done).length;
    const percentage = total > 0 ? (done / total) * 100 : 0;
    const isSuccess = percentage >= 80;

    const changeMonth = (offset: number) => {
        const nextMonth = new Date(viewYear, viewMonth + offset, 1);
        setViewDate(nextMonth);
    };

    const handleDateClick = (day: number) => {
        // Format YYYY-MM-DD using viewYear and viewMonth
        const yyyy = viewYear;
        const mm = String(viewMonth + 1).padStart(2, '0');
        const dd = String(day).padStart(2, '0');
        const dateStr = `${yyyy}-${mm}-${dd}`;
        onSelectDate(dateStr);
    };

    return (
        <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between pb-2 border-b border-border-dark">
                <div className="flex items-center gap-2">
                    <div className="relative flex items-center cursor-pointer group" onClick={() => dateInputRef.current?.showPicker()}> {/* Added flex items-center and onClick */}
                        <span className="material-symbols-outlined text-[#92a4c9] group-hover:text-primary transition-colors">calendar_today</span>
                        <input
                            ref={dateInputRef} // Added ref
                            type="date"
                            className="absolute inset-0 opacity-0 pointer-events-none" // Changed cursor-pointer to pointer-events-none
                            onChange={(e) => {
                                if (e.target.value) {
                                    onSelectDate(e.target.value);
                                    setViewDate(new Date(e.target.value));
                                }
                            }}
                        />
                    </div>
                    <h2 className="text-[#92a4c9] text-sm font-bold uppercase tracking-wider">Schedule</h2>
                </div>
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-1">
                        <button onClick={() => changeMonth(-1)} className="p-1 hover:bg-white/5 rounded text-[#92a4c9] hover:text-white transition-colors">
                            <span className="material-symbols-outlined text-sm">chevron_left</span>
                        </button>
                        <div className="relative flex items-center cursor-pointer group/picker p-1 rounded hover:bg-white/5 transition-colors" onClick={() => monthInputRef.current?.showPicker()}>
                            <span className="text-sm font-semibold text-white w-[110px] text-center hover:text-primary transition-colors inline-block whitespace-nowrap">
                                {monthName} {viewYear}
                            </span>
                            <input
                                ref={monthInputRef}
                                type="month"
                                className="absolute inset-0 opacity-0 pointer-events-none"
                                value={`${viewYear}-${String(viewMonth + 1).padStart(2, '0')}`}
                                onChange={(e) => {
                                    if (e.target.value) {
                                        const [y, m] = e.target.value.split('-').map(Number);
                                        const newDate = new Date(y, m - 1, 1);
                                        setViewDate(newDate);
                                    }
                                }}
                            />
                        </div>
                        <button onClick={() => changeMonth(1)} className="p-1 hover:bg-white/5 rounded text-[#92a4c9] hover:text-white transition-colors">
                            <span className="material-symbols-outlined text-sm">chevron_right</span>
                        </button>
                    </div>
                    <div className={`w-3 h-3 rounded-full shrink-0 shadow-lg ${isSuccess ? 'bg-green-500 shadow-green-500/20' : 'bg-red-500 shadow-red-500/20'}`} title={isSuccess ? "> 80% Done" : "< 80% Done"}></div>
                </div>
            </div>

            <div className="bg-[#1c2636] rounded-xl p-4 border border-border-dark">
                <div className="grid grid-cols-7 gap-1 text-center mb-2">
                    {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map(d => (
                        <div key={d} className="text-[10px] text-[#92a4c9] font-bold uppercase">{d}</div>
                    ))}
                </div>
                <div className="grid grid-cols-7 gap-1 text-center">
                    {Array.from({ length: startDay }).map((_, i) => {
                        const lastDayPrevMonth = new Date(viewYear, viewMonth, 0).getDate();
                        const day = lastDayPrevMonth - startDay + i + 1;
                        return (
                            <div key={`empty-${i}`} className="text-sm text-[#5a6b8c] py-1.5 opacity-20">
                                {day}
                            </div>
                        );
                    })}
                    {Array.from({ length: daysInMonth }).map((_, i) => {
                        const day = i + 1;
                        // Construct date string to compare
                        const mm = String(viewMonth + 1).padStart(2, '0');
                        const dd = String(day).padStart(2, '0');
                        const dateStr = `${viewYear}-${mm}-${dd}`;

                        const isSelected = dateStr === selectedDate;
                        const isTodayHighlight = isCurrentMonth && day === currentDay;
                        const isSuccessDay = (successDays || []).includes(dateStr);

                        // Streak connection logic (horizontal only within the same week/row)
                        const dayOfWeek = (startDay + i) % 7; // 0 = S, 1 = M, ..., 6 = S

                        const hasPrevSuccess = isSuccessDay && dayOfWeek > 0 && day > 1 &&
                            (successDays || []).includes(`${viewYear}-${mm}-${String(day - 1).padStart(2, '0')}`);

                        const hasNextSuccess = isSuccessDay && dayOfWeek < 6 && day < daysInMonth &&
                            (successDays || []).includes(`${viewYear}-${mm}-${String(day + 1).padStart(2, '0')}`);

                        // Style priority: Selected > Success Day > Today > Default
                        let classes = "text-white hover:bg-white/5 rounded transition-all";
                        if (isSelected) {
                            classes = "bg-primary text-white font-bold shadow-lg shadow-primary/30 rounded";
                        } else if (isSuccessDay) {
                            classes = "bg-green-500/20 text-green-500 font-bold border-y border-green-500/30";
                            // Add horizontal borders only on the ends of the streak
                            if (!hasPrevSuccess) classes += " border-l border-l-green-500/30 rounded-l";
                            if (!hasNextSuccess) classes += " border-r border-r-green-500/30 rounded-r";
                            // Negative margins to bridge the gap-1 (4px)
                            if (hasPrevSuccess) classes += " -ml-[5px] pl-[5px]";
                            if (hasNextSuccess) classes += " -mr-[5px] pr-[5px]";
                        } else if (isTodayHighlight) {
                            classes = "text-primary font-semibold border border-primary/30 rounded";
                        }

                        return (
                            <div
                                key={day}
                                onClick={() => handleDateClick(day)}
                                className={`text-sm py-1.5 cursor-pointer relative z-10 ${classes}`}
                            >
                                {day}
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}
