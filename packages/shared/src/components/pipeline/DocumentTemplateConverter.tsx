"use client";

import * as React from "react";
import { CheckCircle2, Download, FileCog, Loader2 } from "lucide-react";

import { pipelineApi } from "../../api/client";
import type {
  APISpecConversionResponse,
  MDSpecValidationErrorPayload,
} from "../../types";
import { Button } from "../ui/Button";
import { toast } from "../ui/Toast";
import { ValidatorFailureChecklist } from "./ValidatorFailureChecklist";

export interface DocumentTemplateConverterProps {
  sourceFile: File;
  llmProfileId?: number | null;
  disabled?: boolean;
  onApply: (file: File) => void;
}

function toValidationError(
  result: APISpecConversionResponse,
): MDSpecValidationErrorPayload | null {
  if (result.validation.valid) return null;
  return {
    error_type: "md_spec_validation",
    code: result.validation.code || "MD_SPEC_VALIDATION_FAILED",
    detail: result.validation.detail || "Converted document needs correction.",
    missing_sections: result.validation.missing_sections,
    missing_fields: result.validation.missing_fields,
    field_errors: result.validation.field_errors.map((item) => ({
      field: item.field,
      message: item.detail,
    })),
  };
}

export function DocumentTemplateConverter({
  sourceFile,
  llmProfileId,
  disabled = false,
  onApply,
}: DocumentTemplateConverterProps) {
  const [baseUrl, setBaseUrl] = React.useState("");
  const [result, setResult] = React.useState<APISpecConversionResponse | null>(null);
  const [draft, setDraft] = React.useState("");
  const [isConverting, setIsConverting] = React.useState(false);

  React.useEffect(() => {
    setResult(null);
    setDraft("");
  }, [sourceFile]);

  const handleConvert = async () => {
    setIsConverting(true);
    try {
      const converted = await pipelineApi.convertDocument(
        sourceFile,
        baseUrl.trim(),
        llmProfileId,
      );
      setResult(converted);
      setDraft(converted.markdown);
      toast.success(
        "Document converted",
        converted.validation.valid
          ? "Review the generated pipeline document, then apply it."
          : "A draft was generated, but some required details still need review.",
      );
    } catch (error) {
      toast.error(
        "Document conversion failed",
        error instanceof Error ? error.message : "Unknown conversion error.",
      );
    } finally {
      setIsConverting(false);
    }
  };

  const handleApply = () => {
    if (!result || !draft.trim()) return;
    onApply(
      new File([draft], result.filename, {
        type: "text/markdown;charset=utf-8",
      }),
    );
    toast.success("Converted document applied", result.filename);
  };

  const handleDownload = () => {
    if (!result || !draft.trim()) return;
    // Save the current draft (including any manual edits) as a local .md file.
    const blob = new Blob([draft], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = result.filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    toast.success("Document downloaded", result.filename);
  };

  const validationError = result ? toValidationError(result) : null;

  return (
    <div className="mt-3 space-y-3 rounded-xl border border-blue-500/20 bg-blue-500/[0.04] p-3">
      <div className="flex items-center gap-2 text-xs font-semibold text-blue-200">
        <FileCog className="h-4 w-4" aria-hidden="true" />
        Convert to pipeline document
      </div>
      <label className="block space-y-1">
        <span className="text-[11px] text-[#92a4c9]">API base URL</span>
        <input
          type="url"
          value={baseUrl}
          onChange={(event) => setBaseUrl(event.target.value)}
          placeholder="http://host.docker.internal:8080"
          disabled={disabled || isConverting}
          className="w-full rounded-lg border border-[#2b3b55] bg-[#101725] px-3 py-2 text-xs text-white outline-none focus:border-blue-500"
        />
      </label>
      <Button
        variant="secondary"
        size="sm"
        fullWidth
        disabled={disabled || isConverting || !baseUrl.trim()}
        onClick={handleConvert}
        leftIcon={
          isConverting ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <FileCog className="h-3.5 w-3.5" />
          )
        }
      >
        {isConverting ? "Converting…" : "Convert document"}
      </Button>

      {result && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-[11px] text-emerald-300">
            <CheckCircle2 className="h-3.5 w-3.5" />
            Generated {result.filename}
          </div>
          {validationError && (
            <ValidatorFailureChecklist structuredError={validationError} />
          )}
          <textarea
            aria-label="Converted pipeline document"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            className="h-56 w-full resize-y rounded-lg border border-[#2b3b55] bg-[#0b111d] p-3 font-mono text-[11px] leading-relaxed text-[#c7d2e8] outline-none focus:border-blue-500"
          />
          <div className="flex gap-2">
            <Button
              variant="primary"
              size="sm"
              className="flex-1"
              disabled={!draft.trim()}
              onClick={handleApply}
            >
              Use converted document
            </Button>
            <Button
              variant="secondary"
              size="sm"
              disabled={!draft.trim()}
              onClick={handleDownload}
              leftIcon={<Download className="h-3.5 w-3.5" />}
            >
              Download
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export default DocumentTemplateConverter;
