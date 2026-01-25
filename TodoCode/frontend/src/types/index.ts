export interface Task {
    id: number;
    title: string;
    is_done: boolean;
    start_time: string;
    end_time: string;
    date: string;
    created_at: string;
    updated_at: string;
}

export interface Goal {
    id: number;
    title: string;
    type: 'day' | 'month' | 'year';
    date?: string;
    month?: string;
    year?: string;
    is_done: boolean;
    created_at: string;
}

export interface Stats {
    daily_goal: number;
    last_5_days: {
        date: string;
        rate: number;
    }[];
    success_days: string[];
}
