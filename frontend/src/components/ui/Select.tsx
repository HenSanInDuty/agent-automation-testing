import * as React from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

// ─────────────────────────────────────────────────────────────────────────────
// Select
// ─────────────────────────────────────────────────────────────────────────────

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps
  extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, "size"> {
  options: SelectOption[];
  placeholder?: string;
  error?: string;
  size?: "sm" | "md" | "lg";
}

const sizeClasses = {
  sm: "h-8 text-xs px-3 pr-8",
  md: "h-9 text-sm px-3 pr-9",
  lg: "h-11 text-base px-4 pr-10",
};

const chevronSize = {
  sm: "w-3.5 h-3.5 right-2",
  md: "w-4 h-4 right-2.5",
  lg: "w-5 h-5 right-3",
};

const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  (
    {
      className,
      options,
      placeholder,
      error,
      size = "md",
      disabled,
      ...props
    },
    ref
  ) => (
    <div className="relative w-full">
      <select
        ref={ref}
        disabled={disabled}
        className={cn(
          // Base
          "w-full appearance-none rounded-lg bg-[#101622] border text-sm text-white",
          "transition-colors duration-150 cursor-pointer",
          // Focus
          "outline-none focus:ring-2 focus:ring-[#135bec] focus:ring-offset-0",
          // Border
          error
            ? "border-[#ef4444] focus:ring-[#ef4444]"
            : "border-[#2b3b55] focus:border-[#135bec]",
          // Size
          sizeClasses[size],
          // Disabled
          disabled && "opacity-50 cursor-not-allowed",
          className
        )}
        {...props}
      >
        {placeholder && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {options.map((opt) => (
          <option key={opt.value} value={opt.value} disabled={opt.disabled}>
            {opt.label}
          </option>
        ))}
      </select>

      {/* Chevron icon */}
      <ChevronDown
        className={cn(
          "absolute top-1/2 -translate-y-1/2 pointer-events-none text-[#92a4c9]",
          chevronSize[size]
        )}
        aria-hidden="true"
      />

      {error && (
        <p className="mt-1.5 text-xs text-[#ef4444]" role="alert">
          {error}
        </p>
      )}
    </div>
  )
);
Select.displayName = "Select";

// ─────────────────────────────────────────────────────────────────────────────
// SelectField – convenience wrapper: Label + Select stacked
// ─────────────────────────────────────────────────────────────────────────────

export interface SelectFieldProps extends SelectProps {
  label: string;
  id: string;
  hint?: string;
}

function SelectField({
  label,
  id,
  hint,
  required,
  error,
  className,
  ...selectProps
}: SelectFieldProps) {
  return (
    <div className={cn("flex flex-col", className)}>
      <label
        htmlFor={id}
        className="block text-sm font-medium text-[#92a4c9] mb-1.5 select-none"
      >
        {label}
        {required && (
          <span className="ml-1 text-[#ef4444]" aria-hidden="true">
            *
          </span>
        )}
      </label>
      <Select id={id} required={required} error={error} {...selectProps} />
      {hint && !error && (
        <p className="mt-1.5 text-xs text-[#3d5070]">{hint}</p>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Badge
// ─────────────────────────────────────────────────────────────────────────────

export type BadgeVariant =
  | "default"
  | "primary"
  | "success"
  | "warning"
  | "danger"
  | "info"
  | "outline";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  size?: "xs" | "sm" | "md";
  dot?: boolean;
}

const badgeVariantClasses: Record<BadgeVariant, string> = {
  default: "bg-[#2b3b55] text-[#92a4c9]",
  primary: "bg-[#135bec]/20 text-[#5b9eff] border border-[#135bec]/30",
  success: "bg-[#22c55e]/15 text-[#4ade80] border border-[#22c55e]/30",
  warning: "bg-[#f59e0b]/15 text-[#fbbf24] border border-[#f59e0b]/30",
  danger: "bg-[#ef4444]/15 text-[#f87171] border border-[#ef4444]/30",
  info: "bg-[#06b6d4]/15 text-[#22d3ee] border border-[#06b6d4]/30",
  outline: "bg-transparent text-[#92a4c9] border border-[#2b3b55]",
};

const badgeSizeClasses = {
  xs: "px-1.5 py-0.5 text-[10px] rounded",
  sm: "px-2 py-0.5 text-xs rounded-md",
  md: "px-2.5 py-1 text-sm rounded-md",
};

const dotColorClasses: Record<BadgeVariant, string> = {
  default: "bg-[#92a4c9]",
  primary: "bg-[#5b9eff]",
  success: "bg-[#4ade80]",
  warning: "bg-[#fbbf24]",
  danger: "bg-[#f87171]",
  info: "bg-[#22d3ee]",
  outline: "bg-[#92a4c9]",
};

function Badge({
  variant = "default",
  size = "sm",
  dot = false,
  className,
  children,
  ...props
}: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 font-medium",
        badgeVariantClasses[variant],
        badgeSizeClasses[size],
        className
      )}
      {...props}
    >
      {dot && (
        <span
          className={cn(
            "inline-block w-1.5 h-1.5 rounded-full shrink-0",
            dotColorClasses[variant]
          )}
          aria-hidden="true"
        />
      )}
      {children}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Toggle (Switch)
// ─────────────────────────────────────────────────────────────────────────────

export interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  size?: "sm" | "md";
  label?: string;
  labelPosition?: "left" | "right";
  className?: string;
  id?: string;
}

function Toggle({
  checked,
  onChange,
  disabled = false,
  size = "md",
  label,
  labelPosition = "right",
  className,
  id,
}: ToggleProps) {
  const trackW = size === "sm" ? "w-8" : "w-10";
  const trackH = size === "sm" ? "h-4" : "h-5";
  const thumbW = size === "sm" ? "w-3 h-3" : "w-3.5 h-3.5";
  const thumbTranslate = size === "sm" ? "translate-x-4" : "translate-x-5";
  const thumbOffset = size === "sm" ? "translate-x-0.5" : "translate-x-0.5";

  const toggle = (
    <button
      type="button"
      role="switch"
      id={id}
      aria-checked={checked}
      disabled={disabled}
      onClick={() => !disabled && onChange(!checked)}
      className={cn(
        "relative inline-flex shrink-0 cursor-pointer rounded-full transition-colors duration-200 ease-in-out",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec] focus-visible:ring-offset-2 focus-visible:ring-offset-[#101622]",
        trackW,
        trackH,
        checked ? "bg-[#135bec]" : "bg-[#2b3b55]",
        disabled && "opacity-50 cursor-not-allowed"
      )}
    >
      <span className="sr-only">{label ?? (checked ? "On" : "Off")}</span>
      <span
        className={cn(
          "pointer-events-none inline-block rounded-full bg-white shadow-sm transform transition-transform duration-200 ease-in-out",
          "absolute top-1/2 -translate-y-1/2",
          thumbW,
          thumbOffset,
          checked ? thumbTranslate : "translate-x-0.5"
        )}
      />
    </button>
  );

  if (!label) {
    return <span className={cn("inline-flex items-center", className)}>{toggle}</span>;
  }

  return (
    <label
      className={cn(
        "inline-flex items-center gap-2 cursor-pointer select-none text-sm text-[#92a4c9]",
        disabled && "opacity-50 cursor-not-allowed",
        className
      )}
    >
      {labelPosition === "left" && <span>{label}</span>}
      {toggle}
      {labelPosition === "right" && <span>{label}</span>}
    </label>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Exports
// ─────────────────────────────────────────────────────────────────────────────

export { Select, SelectField, Badge, Toggle };
export default Select;
