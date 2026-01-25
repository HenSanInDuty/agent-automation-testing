'use client';

import { useState, useEffect } from 'react';
import InputSection from '@/components/InputSection';
import ScopeSection from '@/components/ScopeSection';
import TasksSection from '@/components/TasksSection';
import ScheduleSection from '@/components/ScheduleSection';
import VelocitySection from '@/components/VelocitySection';
import { fetchTasks, createTask, updateTask, deleteTask, fetchGoals, createGoal, deleteGoal, fetchStats } from '@/utils/api';
import { Task, Goal, Stats } from '@/types';

export default function Home() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [stats, setStats] = useState<Stats>({ daily_goal: 0, last_5_days: [], success_days: [] });
  const [loading, setLoading] = useState(true);

  // Default to today
  const [selectedDate, setSelectedDate] = useState(() => {
    const today = new Date();
    const mm = String(today.getMonth() + 1).padStart(2, '0');
    const dd = String(today.getDate()).padStart(2, '0');
    return `${today.getFullYear()}-${mm}-${dd}`;
  });

  const loadData = async (date: string, isInitial = false) => {
    try {
      if (isInitial) setLoading(true);
      const [y, m, d] = date.split('-');
      const yearStr = y;
      const monthStr = `${y}-${m}`;

      const [fetchedTasks, fetchedGoals, fetchedStats] = await Promise.all([
        fetchTasks(date),
        fetchGoals({ date: date, month: monthStr, year: yearStr }),
        fetchStats(date, monthStr)
      ]);

      setTasks(fetchedTasks || []);
      setGoals(fetchedGoals || []);
      setStats(fetchedStats || { daily_goal: 0, last_5_days: [], success_days: [] });
    } catch (error) {
      console.error(error);
    } finally {
      if (isInitial) setLoading(false);
    }
  };

  useEffect(() => {
    loadData(selectedDate, tasks.length === 0);
  }, [selectedDate]);

  const handleAddTask = async (title: string, start: string, end: string) => {
    try {
      const newTask = await createTask(title, start, end, selectedDate);

      if (newTask.date === selectedDate) {
        setTasks(prev => [newTask, ...prev]);
      }
      const [y, m] = selectedDate.split('-');
      fetchStats(selectedDate, `${y}-${m}`).then(setStats);
    } catch (error) {
      console.error(error);
    }
  };

  const handleToggleTask = async (id: number, isDone: boolean) => {
    try {
      setTasks(prev => prev.map(t => t.id === id ? { ...t, is_done: isDone } : t));
      await updateTask(id, { is_done: isDone });
      const [y, m] = selectedDate.split('-');
      const newStats = await fetchStats(selectedDate, `${y}-${m}`);
      setStats(newStats);
    } catch (error) {
      console.error(error);
      loadData(selectedDate);
    }
  };

  const handleDeleteTask = async (id: number) => {
    try {
      await deleteTask(id);
      setTasks(prev => prev.filter(t => t.id !== id));
      const [y, m] = selectedDate.split('-');
      const newStats = await fetchStats(selectedDate, `${y}-${m}`);
      setStats(newStats);
    } catch (error) {
      console.error(error);
    }
  };

  const handleAddGoal = async (title: string, type: 'day' | 'month' | 'year') => {
    try {
      const [y, m, d] = selectedDate.split('-');
      const goalData: any = { title, type };
      if (type === 'day') goalData.date = selectedDate;
      if (type === 'month') goalData.month = `${y}-${m}`;
      if (type === 'year') goalData.year = y;

      const newGoal = await createGoal(goalData);
      setGoals(prev => [newGoal, ...prev]);
    } catch (error) {
      console.error(error);
    }
  };

  const handleDeleteGoal = async (id: number) => {
    try {
      await deleteGoal(id);
      setGoals(prev => prev.filter(g => g.id !== id));
    } catch (error) {
      console.error(error);
    }
  };

  const [y, m, d] = selectedDate.split('-').map(Number);
  const displayDate = new Date(y, m - 1, d).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });

  if (loading && tasks.length === 0 && goals.length === 0) return <div className="min-h-screen flex items-center justify-center text-white">Loading...</div>;

  return (
    <div className="layout-container flex h-full grow flex-col max-w-[1440px] mx-auto w-full px-6 md:px-12 py-8">
      <header className="flex flex-col items-center justify-center gap-8 mb-12">
        <div className="text-center flex flex-col gap-2">
          <h1 className="text-white text-5xl font-black leading-tight tracking-[-0.033em] uppercase">My Focus</h1>
          <p className="text-[#92a4c9] text-lg font-normal">{displayDate}</p>
        </div>
        <InputSection onAddTask={handleAddTask} />
      </header>

      <main className="grid grid-cols-1 lg:grid-cols-12 gap-8 flex-1">
        <ScopeSection goals={goals} onAddGoal={handleAddGoal} onDeleteGoal={handleDeleteGoal} selectedDate={selectedDate} />
        <TasksSection tasks={tasks} onToggle={handleToggleTask} onDelete={handleDeleteTask} />
        <aside className="lg:col-span-3 flex flex-col gap-8">
          <ScheduleSection
            tasks={tasks}
            selectedDate={selectedDate}
            onSelectDate={setSelectedDate}
            successDays={stats.success_days}
          />
          <VelocitySection stats={stats} />
        </aside>
      </main>
    </div>
  );
}
