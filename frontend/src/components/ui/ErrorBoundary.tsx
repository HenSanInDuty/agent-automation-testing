"use client";

import * as React from "react";
import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
  onError?: (error: Error, errorInfo: React.ErrorInfo) => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Default fallback UI
// ─────────────────────────────────────────────────────────────────────────────

function DefaultFallback({
  error,
  onReset,
}: {
  error: Error | null;
  onReset: () => void;
}) {
  return (
    <div className="flex min-h-60 w-full items-center justify-center p-6">
      <div
        className={cn(
          "flex w-full max-w-md flex-col items-center gap-4 rounded-xl p-6 text-center",
          "bg-[#18202F] border border-[#2b3b55]",
          "shadow-lg",
        )}
      >
        {/* Icon */}
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[#ef4444]/10 border border-[#ef4444]/20">
          <AlertTriangle
            className="h-6 w-6 text-[#ef4444]"
            aria-hidden="true"
          />
        </div>

        {/* Heading */}
        <div className="space-y-1">
          <h2 className="text-base font-semibold text-white">
            Something went wrong
          </h2>
          {error?.message && (
            <p className="text-sm text-[#f87171] leading-relaxed">
              {error.message}
            </p>
          )}
        </div>

        {/* Reset button */}
        <button
          type="button"
          onClick={onReset}
          className={cn(
            "mt-1 inline-flex h-9 items-center justify-center gap-2",
            "rounded-lg border border-[#2b3b55] bg-[#1e2a3d]",
            "px-4 text-sm font-medium text-white",
            "hover:bg-[#263450] hover:border-[#3d5070]",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec] focus-visible:ring-offset-2 focus-visible:ring-offset-[#101622]",
            "transition-colors duration-150 cursor-pointer",
          )}
        >
          Try again
        </button>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ErrorBoundary class component
// ─────────────────────────────────────────────────────────────────────────────

export class ErrorBoundary extends React.Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    // Log to console in development
    if (process.env.NODE_ENV !== "production") {
      console.error("[ErrorBoundary] Caught error:", error, errorInfo);
    }

    // Notify the caller if a handler was provided
    this.props.onError?.(error, errorInfo);
  }

  private handleReset = (): void => {
    this.setState({ hasError: false, error: null });
  };

  render(): React.ReactNode {
    if (this.state.hasError) {
      // Use the custom fallback if provided
      if (this.props.fallback !== undefined) {
        return this.props.fallback;
      }

      // Otherwise render the default fallback UI
      return (
        <DefaultFallback error={this.state.error} onReset={this.handleReset} />
      );
    }

    return this.props.children;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// withErrorBoundary HOC
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Higher-order component that wraps `WrappedComponent` in an `ErrorBoundary`.
 *
 * @example
 * const SafeWidget = withErrorBoundary(Widget);
 * const SafeWidget = withErrorBoundary(Widget, { fallback: <p>Oops</p> });
 */
export function withErrorBoundary<P extends object>(
  WrappedComponent: React.ComponentType<P>,
  boundaryProps?: Omit<ErrorBoundaryProps, "children">,
): React.FC<P> {
  const displayName =
    WrappedComponent.displayName ?? WrappedComponent.name ?? "Component";

  function WithErrorBoundaryWrapper(props: P) {
    return (
      <ErrorBoundary {...boundaryProps}>
        <WrappedComponent {...props} />
      </ErrorBoundary>
    );
  }

  WithErrorBoundaryWrapper.displayName = `withErrorBoundary(${displayName})`;

  return WithErrorBoundaryWrapper;
}

export default ErrorBoundary;
