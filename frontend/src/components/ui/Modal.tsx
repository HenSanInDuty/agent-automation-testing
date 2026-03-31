import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export type ModalSize = "sm" | "md" | "lg" | "xl" | "2xl" | "full";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  /** Prevent closing when clicking the backdrop */
  disableBackdropClose?: boolean;
  /** Prevent closing when pressing Escape */
  disableEscapeClose?: boolean;
  size?: ModalSize;
  className?: string;
  children: React.ReactNode;
}

export interface ModalHeaderProps {
  title: string;
  subtitle?: string;
  onClose?: () => void;
  className?: string;
  icon?: React.ReactNode;
}

export interface ModalBodyProps {
  className?: string;
  children: React.ReactNode;
  /** Remove default padding */
  noPadding?: boolean;
}

export interface ModalFooterProps {
  className?: string;
  children: React.ReactNode;
  /** Align buttons: left | center | right (default: right) */
  align?: "left" | "center" | "right";
}

// ─────────────────────────────────────────────────────────────────────────────
// Size map
// ─────────────────────────────────────────────────────────────────────────────

const sizeClasses: Record<ModalSize, string> = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-lg",
  xl: "max-w-xl",
  "2xl": "max-w-2xl",
  full: "max-w-[calc(100vw-2rem)] max-h-[calc(100vh-2rem)]",
};

// ─────────────────────────────────────────────────────────────────────────────
// Modal (root)
// ─────────────────────────────────────────────────────────────────────────────

function Modal({
  open,
  onClose,
  disableBackdropClose = false,
  disableEscapeClose = false,
  size = "md",
  className,
  children,
}: ModalProps) {
  // Close on Escape key
  React.useEffect(() => {
    if (!open || disableEscapeClose) return;

    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };

    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose, disableEscapeClose]);

  // Lock body scroll while modal is open
  React.useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        aria-hidden="true"
        onClick={disableBackdropClose ? undefined : onClose}
      />

      {/* Panel */}
      <div
        className={cn(
          // Layout
          "relative z-10 w-full flex flex-col",
          // Visual
          "bg-[#18202F] border border-[#2b3b55] rounded-2xl shadow-2xl",
          // Max height
          "max-h-[90vh]",
          // Animation
          "animate-in fade-in zoom-in-95 duration-200",
          // Size
          sizeClasses[size],
          className
        )}
        // Prevent clicks inside the panel from bubbling to the backdrop
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ModalHeader
// ─────────────────────────────────────────────────────────────────────────────

function ModalHeader({
  title,
  subtitle,
  onClose,
  className,
  icon,
}: ModalHeaderProps) {
  return (
    <div
      className={cn(
        "flex items-start justify-between gap-4 px-6 py-5",
        "border-b border-[#2b3b55] shrink-0",
        className
      )}
    >
      <div className="flex items-center gap-3 min-w-0">
        {icon && (
          <div className="shrink-0 w-9 h-9 rounded-lg bg-[#135bec]/10 border border-[#135bec]/20 flex items-center justify-center text-[#5b9eff]">
            {icon}
          </div>
        )}
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-white leading-tight truncate">
            {title}
          </h2>
          {subtitle && (
            <p className="mt-0.5 text-sm text-[#92a4c9] leading-snug truncate">
              {subtitle}
            </p>
          )}
        </div>
      </div>

      {onClose && (
        <button
          type="button"
          onClick={onClose}
          aria-label="Close dialog"
          className={cn(
            "shrink-0 p-1.5 rounded-lg text-[#92a4c9]",
            "hover:bg-[#2b3b55] hover:text-white",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec]",
            "transition-colors duration-150"
          )}
        >
          <X className="w-4 h-4" aria-hidden="true" />
        </button>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ModalBody
// ─────────────────────────────────────────────────────────────────────────────

function ModalBody({ className, children, noPadding = false }: ModalBodyProps) {
  return (
    <div
      className={cn(
        "flex-1 overflow-y-auto",
        // Custom scrollbar
        "[&::-webkit-scrollbar]:w-1.5",
        "[&::-webkit-scrollbar-track]:bg-transparent",
        "[&::-webkit-scrollbar-thumb]:bg-[#2b3b55] [&::-webkit-scrollbar-thumb]:rounded-full",
        !noPadding && "px-6 py-5",
        className
      )}
    >
      {children}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ModalFooter
// ─────────────────────────────────────────────────────────────────────────────

const footerAlignClasses: Record<NonNullable<ModalFooterProps["align"]>, string> = {
  left: "justify-start",
  center: "justify-center",
  right: "justify-end",
};

function ModalFooter({
  className,
  children,
  align = "right",
}: ModalFooterProps) {
  return (
    <div
      className={cn(
        "flex items-center gap-3 px-6 py-4",
        "border-t border-[#2b3b55] shrink-0",
        footerAlignClasses[align],
        className
      )}
    >
      {children}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ModalDivider – thin separator inside ModalBody
// ─────────────────────────────────────────────────────────────────────────────

function ModalDivider({ className }: { className?: string }) {
  return (
    <hr
      className={cn("border-t border-[#2b3b55] my-4 -mx-6", className)}
      aria-hidden="true"
    />
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Confirm Dialog – convenient shorthand for yes/no confirmations
// ─────────────────────────────────────────────────────────────────────────────

export interface ConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "danger" | "primary";
  loading?: boolean;
}

function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  variant = "danger",
  loading = false,
}: ConfirmDialogProps) {
  const confirmBtnClasses =
    variant === "danger"
      ? "bg-[#ef4444] hover:bg-[#dc2626] text-white border border-[#ef4444]"
      : "bg-[#135bec] hover:bg-[#1a6aff] text-white border border-[#135bec]";

  return (
    <Modal open={open} onClose={onClose} size="sm">
      <ModalHeader title={title} onClose={onClose} />
      {description && (
        <ModalBody>
          <p className="text-sm text-[#92a4c9] leading-relaxed">{description}</p>
        </ModalBody>
      )}
      <ModalFooter>
        <button
          type="button"
          onClick={onClose}
          disabled={loading}
          className={cn(
            "h-9 px-4 text-sm font-medium rounded-lg transition-colors duration-150",
            "bg-transparent border border-[#2b3b55] text-white",
            "hover:bg-[#1e2a3d] hover:border-[#3d5070]",
            "disabled:opacity-50 disabled:cursor-not-allowed"
          )}
        >
          {cancelLabel}
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={loading}
          className={cn(
            "h-9 px-4 text-sm font-medium rounded-lg transition-colors duration-150",
            "inline-flex items-center gap-2",
            confirmBtnClasses,
            "disabled:opacity-50 disabled:cursor-not-allowed"
          )}
        >
          {loading && (
            <svg
              className="w-4 h-4 animate-spin"
              fill="none"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
          )}
          {confirmLabel}
        </button>
      </ModalFooter>
    </Modal>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Exports
// ─────────────────────────────────────────────────────────────────────────────

export {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  ModalDivider,
  ConfirmDialog,
};
export default Modal;
