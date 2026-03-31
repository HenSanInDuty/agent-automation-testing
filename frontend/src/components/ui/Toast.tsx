"use client";

import * as React from "react";
import { X, CheckCircle, XCircle, AlertTriangle, Info } from "lucide-react";
import { cn } from "@/lib/utils";

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export type ToastType = "success" | "error" | "warning" | "info";

export interface Toast {
  id: string;
  type: ToastType;
  title: string;
  description?: string;
  duration?: number; // ms — 0 = persistent
}

export type ToastInput = Omit<Toast, "id">;

// ─────────────────────────────────────────────────────────────────────────────
// Internal event bus (module-level so it works outside React tree)
// ─────────────────────────────────────────────────────────────────────────────

type Listener = (toasts: Toast[]) => void;

let _toasts: Toast[] = [];
const _listeners = new Set<Listener>();

function _notify() {
  _listeners.forEach((l) => l([..._toasts]));
}

function _addToast(input: ToastInput): string {
  const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  const toast: Toast = { duration: 4000, ...input, id };
  _toasts = [toast, ..._toasts].slice(0, 5); // max 5 toasts
  _notify();

  if (toast.duration && toast.duration > 0) {
    setTimeout(() => _removeToast(id), toast.duration);
  }

  return id;
}

function _removeToast(id: string) {
  _toasts = _toasts.filter((t) => t.id !== id);
  _notify();
}

// ─────────────────────────────────────────────────────────────────────────────
// Public toast() API — call from anywhere (no hook needed)
// ─────────────────────────────────────────────────────────────────────────────

export const toast = {
  success: (title: string, description?: string, duration?: number) =>
    _addToast({ type: "success", title, description, duration }),

  error: (title: string, description?: string, duration?: number) =>
    _addToast({ type: "error", title, description, duration: duration ?? 6000 }),

  warning: (title: string, description?: string, duration?: number) =>
    _addToast({ type: "warning", title, description, duration }),

  info: (title: string, description?: string, duration?: number) =>
    _addToast({ type: "info", title, description, duration }),

  dismiss: (id: string) => _removeToast(id),

  dismissAll: () => {
    _toasts = [];
    _notify();
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// useToasts hook — subscribes to the toast store
// ─────────────────────────────────────────────────────────────────────────────

export function useToasts() {
  const [toasts, setToasts] = React.useState<Toast[]>([..._toasts]);

  React.useEffect(() => {
    const listener: Listener = (updated) => setToasts(updated);
    _listeners.add(listener);
    return () => {
      _listeners.delete(listener);
    };
  }, []);

  return { toasts, dismiss: _removeToast, dismissAll: toast.dismissAll };
}

// ─────────────────────────────────────────────────────────────────────────────
// Visual config per type
// ─────────────────────────────────────────────────────────────────────────────

const typeConfig: Record<
  ToastType,
  {
    icon: React.ReactNode;
    barColor: string;
    iconColor: string;
    borderColor: string;
  }
> = {
  success: {
    icon: <CheckCircle className="w-4 h-4" aria-hidden="true" />,
    iconColor: "text-[#4ade80]",
    barColor: "bg-[#22c55e]",
    borderColor: "border-[#22c55e]/30",
  },
  error: {
    icon: <XCircle className="w-4 h-4" aria-hidden="true" />,
    iconColor: "text-[#f87171]",
    barColor: "bg-[#ef4444]",
    borderColor: "border-[#ef4444]/30",
  },
  warning: {
    icon: <AlertTriangle className="w-4 h-4" aria-hidden="true" />,
    iconColor: "text-[#fbbf24]",
    barColor: "bg-[#f59e0b]",
    borderColor: "border-[#f59e0b]/30",
  },
  info: {
    icon: <Info className="w-4 h-4" aria-hidden="true" />,
    iconColor: "text-[#22d3ee]",
    barColor: "bg-[#06b6d4]",
    borderColor: "border-[#06b6d4]/30",
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Single Toast item
// ─────────────────────────────────────────────────────────────────────────────

interface ToastItemProps {
  toast: Toast;
  onDismiss: (id: string) => void;
}

function ToastItem({ toast, onDismiss }: ToastItemProps) {
  const [visible, setVisible] = React.useState(false);
  const config = typeConfig[toast.type];

  // Trigger entrance animation on mount
  React.useEffect(() => {
    const raf = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div
      role="alert"
      aria-live="assertive"
      aria-atomic="true"
      className={cn(
        // Layout
        "relative flex items-start gap-3 w-full max-w-sm",
        "px-4 py-3.5 rounded-xl overflow-hidden",
        // Visual
        "bg-[#18202F] border shadow-xl shadow-black/40",
        config.borderColor,
        // Transition
        "transition-all duration-300 ease-out",
        visible
          ? "opacity-100 translate-x-0"
          : "opacity-0 translate-x-4"
      )}
    >
      {/* Coloured left bar */}
      <span
        className={cn(
          "absolute left-0 inset-y-0 w-1 rounded-l-xl",
          config.barColor
        )}
        aria-hidden="true"
      />

      {/* Icon */}
      <span className={cn("mt-0.5 shrink-0", config.iconColor)}>
        {config.icon}
      </span>

      {/* Text */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-white leading-snug">
          {toast.title}
        </p>
        {toast.description && (
          <p className="mt-0.5 text-xs text-[#92a4c9] leading-snug">
            {toast.description}
          </p>
        )}
      </div>

      {/* Dismiss button */}
      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        aria-label="Dismiss notification"
        className={cn(
          "shrink-0 p-1 -mr-1 rounded-lg",
          "text-[#92a4c9] hover:text-white",
          "hover:bg-[#2b3b55]",
          "transition-colors duration-150",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec]"
        )}
      >
        <X className="w-3.5 h-3.5" aria-hidden="true" />
      </button>

      {/* Progress bar (only for timed toasts) */}
      {toast.duration && toast.duration > 0 && (
        <span
          className={cn(
            "absolute bottom-0 left-0 h-0.5 rounded-b-xl",
            config.barColor,
            "animate-[shrink_var(--dur)_linear_forwards]"
          )}
          style={
            {
              "--dur": `${toast.duration}ms`,
              width: "100%",
            } as React.CSSProperties
          }
          aria-hidden="true"
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Toaster – place once in the app root layout
// ─────────────────────────────────────────────────────────────────────────────

export function Toaster() {
  const { toasts, dismiss } = useToasts();

  if (toasts.length === 0) return null;

  return (
    <div
      aria-label="Notifications"
      className={cn(
        "fixed bottom-5 right-5 z-[9999]",
        "flex flex-col-reverse gap-2 items-end",
        "pointer-events-none"
      )}
    >
      {toasts.map((t) => (
        <div key={t.id} className="pointer-events-auto">
          <ToastItem toast={t} onDismiss={dismiss} />
        </div>
      ))}
    </div>
  );
}

export default Toaster;
