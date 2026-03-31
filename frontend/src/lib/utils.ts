import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format a datetime string to a human-readable format.
 * e.g. "2025-01-15T10:30:00Z" → "Jan 15, 2025 10:30"
 */
export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Format a datetime string to a relative time string.
 * e.g. "3 minutes ago", "2 hours ago"
 */
export function formatRelativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

/**
 * Truncate a string to a given max length, appending "…" if truncated.
 */
export function truncate(str: string, max: number): string {
  if (str.length <= max) return str;
  return str.slice(0, max - 1) + "…";
}

/**
 * Convert a snake_case string to Title Case.
 * e.g. "requirement_analyzer" → "Requirement Analyzer"
 */
export function snakeToTitle(str: string): string {
  return str
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

/**
 * Sleep for a given number of milliseconds.
 * Useful for testing loading states.
 */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Get initials from a name string.
 * e.g. "GPT-4o Production" → "GP"
 */
export function getInitials(name: string, max = 2): string {
  return name
    .split(/[\s-_]+/)
    .slice(0, max)
    .map((w) => w.charAt(0).toUpperCase())
    .join("");
}
