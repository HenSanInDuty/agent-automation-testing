import { Goal, Task } from '@/types';

const API_URL = 'http://localhost:8080/api';

export async function fetchTasks(date?: string) {
    const url = date ? `${API_URL}/tasks?date=${date}` : `${API_URL}/tasks`;
    const res = await fetch(url);
    if (!res.ok) throw new Error('Failed to fetch tasks');
    return res.json();
}

export async function createTask(title: string, start: string, end: string, date: string) {
    const res = await fetch(`${API_URL}/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, start_time: start, end_time: end, date }),
    });
    if (!res.ok) throw new Error('Failed to create task');
    return res.json();
}

export async function updateTask(id: number, updates: any) {
    const res = await fetch(`${API_URL}/tasks/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
    });
    if (!res.ok) throw new Error('Failed to update task');
    return res.json();
}

export async function deleteTask(id: number) {
    const res = await fetch(`${API_URL}/tasks/${id}`, {
        method: 'DELETE',
    });
    if (!res.ok) throw new Error('Failed to delete task');
    return res.json();
}

export async function fetchGoals(filters: { type?: string, date?: string, month?: string, year?: string } = {}) {
    const params = new URLSearchParams();
    if (filters.type) params.append('type', filters.type);
    if (filters.date) params.append('date', filters.date);
    if (filters.month) params.append('month', filters.month);
    if (filters.year) params.append('year', filters.year);

    const url = `${API_URL}/goals?${params.toString()}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error('Failed to fetch goals');
    return res.json();
}

export async function createGoal(goal: Partial<Goal>) {
    const res = await fetch(`${API_URL}/goals`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(goal),
    });
    if (!res.ok) throw new Error('Failed to create goal');
    return res.json();
}

export async function deleteGoal(id: number) {
    const res = await fetch(`${API_URL}/goals/${id}`, {
        method: 'DELETE',
    });
    if (!res.ok) throw new Error('Failed to delete goal');
    return res.json();
}

export async function fetchStats(date?: string, month?: string) {
    const params = new URLSearchParams();
    if (date) params.append('date', date);
    if (month) params.append('month', month);

    const url = `${API_URL}/stats?${params.toString()}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error('Failed to fetch stats');
    return res.json();
}
