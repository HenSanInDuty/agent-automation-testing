import * as React from "react";
import { cn } from "@/lib/utils";

// ─────────────────────────────────────────────────────────────────────────────
// Label
// ─────────────────────────────────────────────────────────────────────────────

export interface LabelProps
  extends React.LabelHTMLAttributes<HTMLLabelElement> {
  required?: boolean;
}

const Label = React.forwardRef<HTMLLabelElement, LabelProps>(
  ({ className, children, required, ...props }, ref) => (
    <label
      ref={ref}
      className={cn(
        "block text-sm font-medium text-[#92a4c9] mb-1.5 select-none",
        className
      )}
      {...props}
    >
      {children}
      {required && (
        <span className="ml-1 text-[#ef4444]" aria-hidden="true">
          *
        </span>
      )}
    </label>
  )
);
Label.displayName = "Label";

// ─────────────────────────────────────────────────────────────────────────────
// Input
// ─────────────────────────────────────────────────────────────────────────────

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {
  error?: string;
  leftElement?: React.ReactNode;
  rightElement?: React.ReactNode;
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, error, leftElement, rightElement, type = "text", ...props }, ref) => {
    const hasLeft = Boolean(leftElement);
    const hasRight = Boolean(rightElement);

    return (
      <div className="w-full">
        <div className="relative flex items-center">
          {hasLeft && (
            <div className="absolute left-3 flex items-center pointer-events-none text-[#92a4c9]">
              {leftElement}
            </div>
          )}

          <input
            ref={ref}
            type={type}
            className={cn(
              // Base
              "w-full h-9 rounded-lg bg-[#101622] border text-sm text-white",
              "placeholder:text-[#3d5070]",
              "transition-colors duration-150",
              // Focus
              "outline-none focus:ring-2 focus:ring-[#135bec] focus:ring-offset-0",
              // Border
              error
                ? "border-[#ef4444] focus:ring-[#ef4444]"
                : "border-[#2b3b55] focus:border-[#135bec]",
              // Padding - adjust for icons
              hasLeft ? "pl-9" : "px-3",
              hasRight ? "pr-9" : "px-3",
              // Disabled
              "disabled:opacity-50 disabled:cursor-not-allowed",
              className
            )}
            {...props}
          />

          {hasRight && (
            <div className="absolute right-3 flex items-center text-[#92a4c9]">
              {rightElement}
            </div>
          )}
        </div>

        {error && (
          <p className="mt-1.5 text-xs text-[#ef4444]" role="alert">
            {error}
          </p>
        )}
      </div>
    );
  }
);
Input.displayName = "Input";

// ─────────────────────────────────────────────────────────────────────────────
// Textarea
// ─────────────────────────────────────────────────────────────────────────────

export interface TextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  error?: string;
}

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, error, ...props }, ref) => (
    <div className="w-full">
      <textarea
        ref={ref}
        rows={props.rows ?? 3}
        className={cn(
          // Base
          "w-full rounded-lg bg-[#101622] border text-sm text-white px-3 py-2",
          "placeholder:text-[#3d5070]",
          "transition-colors duration-150 resize-y",
          // Focus
          "outline-none focus:ring-2 focus:ring-[#135bec] focus:ring-offset-0",
          // Border
          error
            ? "border-[#ef4444] focus:ring-[#ef4444]"
            : "border-[#2b3b55] focus:border-[#135bec]",
          // Disabled
          "disabled:opacity-50 disabled:cursor-not-allowed",
          className
        )}
        {...props}
      />

      {error && (
        <p className="mt-1.5 text-xs text-[#ef4444]" role="alert">
          {error}
        </p>
      )}
    </div>
  )
);
Textarea.displayName = "Textarea";

// ─────────────────────────────────────────────────────────────────────────────
// FormField – convenience wrapper: Label + Input stacked
// ─────────────────────────────────────────────────────────────────────────────

export interface FormFieldProps extends InputProps {
  label: string;
  id: string;
  hint?: string;
}

const FormField = React.forwardRef<HTMLInputElement, FormFieldProps>(
  ({ label, id, hint, required, error, className, ...inputProps }, ref) => (
    <div className={cn("flex flex-col", className)}>
      <Label htmlFor={id} required={required}>
        {label}
      </Label>
      <Input ref={ref} id={id} required={required} error={error} {...inputProps} />
      {hint && !error && (
        <p className="mt-1.5 text-xs text-[#3d5070]">{hint}</p>
      )}
    </div>
  )
);
FormField.displayName = "FormField";

// ─────────────────────────────────────────────────────────────────────────────
// TextareaField – convenience wrapper: Label + Textarea stacked
// ─────────────────────────────────────────────────────────────────────────────

export interface TextareaFieldProps extends TextareaProps {
  label: string;
  id: string;
  hint?: string;
}

const TextareaField = React.forwardRef<HTMLTextAreaElement, TextareaFieldProps>(
  ({ label, id, hint, required, error, className, ...textareaProps }, ref) => (
    <div className={cn("flex flex-col", className)}>
      <Label htmlFor={id} required={required}>
        {label}
      </Label>
      <Textarea ref={ref} id={id} required={required} error={error} {...textareaProps} />
      {hint && !error && (
        <p className="mt-1.5 text-xs text-[#3d5070]">{hint}</p>
      )}
    </div>
  )
);
TextareaField.displayName = "TextareaField";

export { Label, Input, Textarea, FormField, TextareaField };
export default Input;
