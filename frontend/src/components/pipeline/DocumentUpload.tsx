"use client";

import * as React from "react";
import { Upload, FileText, X, AlertCircle } from "lucide-react";

import { cn } from "@/lib/utils";

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const DEFAULT_ACCEPT = ".pdf,.docx,.xlsx,.xls,.png,.jpg,.jpeg,.webp,.md,.txt";
const DEFAULT_MAX_SIZE_MB = 50;

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getFileExtension(filename: string): string {
  const parts = filename.split(".");
  return parts.length > 1 ? "." + parts.pop()!.toLowerCase() : "";
}

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

export interface DocumentUploadProps {
  file: File | null;
  onChange: (file: File | null) => void;
  disabled?: boolean;
  /** Comma-separated list of accepted file extensions. */
  accept?: string;
  /** Maximum allowed file size in megabytes. Defaults to 50. */
  maxSizeMb?: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// DocumentUpload
// ─────────────────────────────────────────────────────────────────────────────

export function DocumentUpload({
  file,
  onChange,
  disabled = false,
  accept = DEFAULT_ACCEPT,
  maxSizeMb = DEFAULT_MAX_SIZE_MB,
}: DocumentUploadProps) {
  const [isDragging, setIsDragging] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);

  const maxSizeBytes = maxSizeMb * 1024 * 1024;

  // Accepted extensions as a normalised set for fast lookup
  const acceptedExts = React.useMemo(
    () => new Set(accept.split(",").map((s) => s.trim().toLowerCase())),
    [accept],
  );

  // Human-readable format list shown in the drop-zone
  const acceptedFormatsLabel = accept
    .split(",")
    .map((s) => s.trim().replace(".", "").toUpperCase())
    .join(", ");

  // ── Validation + commit ───────────────────────────────────────────────────

  const validateAndCommit = React.useCallback(
    (incoming: File) => {
      setError(null);

      // Type check
      const ext = getFileExtension(incoming.name);
      if (ext && !acceptedExts.has(ext)) {
        setError(
          `File type "${ext}" is not supported. Accepted formats: ${accept}`,
        );
        return;
      }

      // Size check
      if (incoming.size > maxSizeBytes) {
        setError(
          `File is too large (${formatFileSize(incoming.size)}). Maximum allowed size is ${maxSizeMb} MB.`,
        );
        return;
      }

      onChange(incoming);
    },
    [accept, acceptedExts, maxSizeBytes, maxSizeMb, onChange],
  );

  // ── Event handlers ────────────────────────────────────────────────────────

  const handleZoneClick = () => {
    if (disabled) return;
    inputRef.current?.click();
  };

  const handleZoneKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      handleZoneClick();
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) validateAndCommit(selected);
    // Reset so selecting the same file again triggers onChange
    e.target.value = "";
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (!disabled) setIsDragging(true);
  };

  const handleDragEnter = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (!disabled) setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (disabled) return;

    const dropped = e.dataTransfer.files[0];
    if (!dropped) return;
    validateAndCommit(dropped);
  };

  const handleClear = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    onChange(null);
    setError(null);
  };

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="w-full">
      {/* Hidden file input */}
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="sr-only"
        onChange={handleInputChange}
        disabled={disabled}
        aria-hidden="true"
        tabIndex={-1}
      />

      {/* ── Drop zone ────────────────────────────────────────────────────── */}
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-label={
          file
            ? `Selected file: ${file.name}. Click to change.`
            : "Click or drag a file to upload"
        }
        aria-disabled={disabled}
        onClick={handleZoneClick}
        onKeyDown={handleZoneKeyDown}
        onDragOver={handleDragOver}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={cn(
          // Base
          "relative flex flex-col items-center justify-center",
          "rounded-xl border-2 border-dashed",
          "min-h-42 px-6 py-8",
          "transition-all duration-200 ease-out",
          "select-none outline-none",
          // Default surface
          "bg-[#18202F] border-[#2b3b55]",
          // Drag-over tint
          isDragging && !disabled
            ? "border-[#135bec] bg-[#135bec]/5 shadow-[inset_0_0_0_1px_rgba(19,91,236,0.15)]"
            : !disabled && "hover:border-[#135bec]/55 hover:bg-[#1e2a3d]",
          // Focus ring
          "focus-visible:ring-2 focus-visible:ring-[#135bec] focus-visible:ring-offset-2 focus-visible:ring-offset-[#101622]",
          // Disabled
          disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer",
        )}
      >
        {file ? (
          // ── File selected state ──────────────────────────────────────────
          <>
            {/* Clear button */}
            {!disabled && (
              <button
                type="button"
                onClick={handleClear}
                aria-label="Remove selected file"
                className={cn(
                  "absolute top-2.5 right-2.5",
                  "flex items-center justify-center w-7 h-7 rounded-lg",
                  "bg-[#2b3b55] hover:bg-[#ef4444]/20",
                  "text-[#92a4c9] hover:text-[#f87171]",
                  "transition-colors duration-150",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec]",
                )}
              >
                <X className="w-3.5 h-3.5" aria-hidden="true" />
              </button>
            )}

            <div className="flex flex-col items-center gap-3 text-center">
              {/* File icon */}
              <div
                className={cn(
                  "flex items-center justify-center w-12 h-12 rounded-xl",
                  "bg-[#135bec]/15 border border-[#135bec]/25",
                  "transition-transform duration-200",
                  !disabled && "group-hover:scale-105",
                )}
              >
                <FileText
                  className="w-6 h-6 text-[#5b9eff]"
                  aria-hidden="true"
                />
              </div>

              {/* File name + size */}
              <div>
                <p
                  className="text-sm font-medium text-white truncate max-w-60"
                  title={file.name}
                >
                  {file.name}
                </p>
                <p className="mt-0.5 text-xs text-[#92a4c9]">
                  {formatFileSize(file.size)}
                </p>
              </div>

              {/* Change hint */}
              {!disabled && (
                <p className="text-[11px] text-[#3d5070]">
                  Click to replace or drag a new file
                </p>
              )}
            </div>
          </>
        ) : (
          // ── Empty / awaiting file state ──────────────────────────────────
          <div className="flex flex-col items-center gap-3 text-center">
            {/* Upload icon */}
            <div
              className={cn(
                "flex items-center justify-center w-12 h-12 rounded-xl",
                "border transition-all duration-200",
                isDragging && !disabled
                  ? "bg-[#135bec]/20 border-[#135bec]/40"
                  : "bg-[#1e2a3d] border-[#2b3b55]",
              )}
            >
              <Upload
                className={cn(
                  "w-6 h-6 transition-colors duration-200",
                  isDragging && !disabled ? "text-[#5b9eff]" : "text-[#92a4c9]",
                )}
                aria-hidden="true"
              />
            </div>

            {/* Prompt text */}
            <div>
              <p className="text-sm font-medium text-white">
                {isDragging && !disabled
                  ? "Drop to upload"
                  : "Drag & drop or click to upload"}
              </p>
              <p className="mt-1 text-xs text-[#3d5070]">
                {acceptedFormatsLabel}
              </p>
              <p className="mt-0.5 text-xs text-[#3d5070]">
                Max {maxSizeMb} MB
              </p>
            </div>
          </div>
        )}
      </div>

      {/* ── Error message ─────────────────────────────────────────────────── */}
      {error && (
        <div
          role="alert"
          className="mt-2 flex items-start gap-1.5 text-xs text-[#f87171]"
        >
          <AlertCircle
            className="w-3.5 h-3.5 mt-0.5 shrink-0"
            aria-hidden="true"
          />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}

export default DocumentUpload;
