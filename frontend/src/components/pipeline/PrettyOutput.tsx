"use client";

import React, { useState } from "react";
import { Copy, Check, ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "@/lib/utils";


const FENCE_RE = /^```(?:json|js|javascript|ts|typescript|text|python)?\s*\n([\s\S]*?)\n?```\s*$/;

function unwrapValue(val: unknown, depth = 0): unknown {
  if (depth > 8) return val;
  if (typeof val === "string") {
    const trimmed = val.trim();
    const fence = FENCE_RE.exec(trimmed);
    if (fence) {
      const inner = fence[1].trim();
      try   { return unwrapValue(JSON.parse(inner), depth + 1); }
      catch { return unwrapValue(inner, depth + 1); }
    }
    if (
      (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
      (trimmed.startsWith("[") && trimmed.endsWith("]"))
    ) {
      try { return unwrapValue(JSON.parse(trimmed), depth + 1); }
      catch { /* keep */ }
    }
    return val;
  }
  if (Array.isArray(val)) return val.map((v) => unwrapValue(v, depth + 1));
  if (val !== null && typeof val === "object") {
    const processed = Object.fromEntries(
      Object.entries(val as Record<string, unknown>).map(([k, v]) => [
        k, unwrapValue(v, depth + 1),
      ]),
    );
    // Hoist single-key "raw_output" wrapper when the inner value is a
    // non-primitive — e.g. {raw_output: {analysis_results: {...}}} → {analysis_results: {...}}
    const keys = Object.keys(processed);
    if (
      keys.length === 1 &&
      keys[0] === "raw_output" &&
      processed["raw_output"] !== null &&
      typeof processed["raw_output"] === "object"
    ) {
      return processed["raw_output"];
    }
    return processed;
  }
  return val;
}

const TOKEN_RE = /"(?:[^"\\]|\\.)*"\s*:|"(?:[^"\\]|\\.)*"|\btrue\b|\bfalse\b|\bnull\b|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/g;
function JsonHighlight({ src }: { src: string }) {
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  TOKEN_RE.lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = TOKEN_RE.exec(src)) !== null) {
    if (match.index > lastIndex) {
      parts.push(
        <span key={"gap-" + lastIndex} className="text-[#8b949e]">
          {src.slice(lastIndex, match.index)}
        </span>,
      );
    }

    const full = match[0];
    let node: React.ReactNode;

    if (full.endsWith(":")) {
      // JSON object key: "someKey":
      // The colon (plus optional whitespace) is at the end; keep it gray
      const colonIdx = full.lastIndexOf(":");
      const strPart = full.slice(0, colonIdx);
      const colon = full.slice(colonIdx);
      node = (
        <span key={match.index}>
          <span className="text-[#7dd3fc]">{strPart}</span>
          <span className="text-[#8b949e]">{colon}</span>
        </span>
      );
    } else if (full.startsWith('"')) {
      // String value
      node = (
        <span key={match.index} className="text-[#a5d6ff]">
          {full}
        </span>
      );
    } else if (full === "true" || full === "false") {
      // Boolean
      node = (
        <span key={match.index} className="text-[#79c0ff]">
          {full}
        </span>
      );
    } else if (full === "null") {
      // Null
      node = (
        <span key={match.index} className="italic text-[#8b949e]">
          {full}
        </span>
      );
    } else {
      // Number
      node = (
        <span key={match.index} className="text-[#ffa657]">
          {full}
        </span>
      );
    }

    parts.push(node);
    lastIndex = TOKEN_RE.lastIndex;
  }

  if (lastIndex < src.length) {
    parts.push(
      <span key="tail" className="text-[#8b949e]">
        {src.slice(lastIndex)}
      </span>,
    );
  }
  return <>{parts}</>;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <button
      type="button"
      onClick={handleCopy}
      title={copied ? "Copied!" : "Copy to clipboard"}
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] text-[#3d5070] hover:text-[#92a4c9] hover:bg-[#1e2a3d] transition-colors"
    >
      {copied ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3" />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

const COLLAPSE_LINES = 20;

export interface PrettyOutputProps {
  value: string;
  className?: string;
}

export function PrettyOutput({ value, className }: PrettyOutputProps) {
  const [expanded, setExpanded] = useState(false);

  let display = value;
  let isJson = false;
  try {
    const parsed = JSON.parse(value);
    const unwrapped = unwrapValue(parsed);
    display = JSON.stringify(unwrapped, null, 2);
    isJson = true;
  } catch {
    display = value;
  }

  const lines = display.split("\n");
  const isTall = lines.length > COLLAPSE_LINES;
  const visible = isTall && !expanded ? lines.slice(0, COLLAPSE_LINES).join("\n") : display;

  return (
    <div className={cn("rounded-lg border border-[#2b3b55] bg-[#0d1117] overflow-hidden", className)}>
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-[#2b3b55] bg-[#161b22]">
        <span className="text-[10px] font-mono uppercase tracking-wider text-[#3d5070]">
          {isJson ? "json" : "text"}
        </span>
        <CopyButton text={display} />
      </div>
      <pre
        className={cn(
          "font-mono text-xs leading-relaxed text-[#c9d1d9] p-4",
          "whitespace-pre-wrap break-words overflow-x-auto",
          "[&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar]:h-1.5",
          "[&::-webkit-scrollbar-track]:bg-transparent",
          "[&::-webkit-scrollbar-thumb]:bg-[#2b3b55] [&::-webkit-scrollbar-thumb]:rounded-full",
        )}
      >
        {isJson ? <JsonHighlight src={visible} /> : visible}
        {isTall && !expanded && <span className="text-[#3d5070]"> \u2026</span>}
      </pre>
      {isTall && (
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          className={cn(
            "flex items-center justify-center gap-1.5 w-full py-2",
            "text-[11px] text-[#3d5070] hover:text-[#92a4c9]",
            "border-t border-[#2b3b55] hover:bg-[#1e2a3d] transition-colors",
          )}
        >
          {expanded ? (
            <><ChevronUp className="w-3 h-3" /> Show less</>
          ) : (
            <><ChevronDown className="w-3 h-3" /> Show {lines.length - COLLAPSE_LINES} more lines</>
          )}
        </button>
      )}
    </div>
  );
}
