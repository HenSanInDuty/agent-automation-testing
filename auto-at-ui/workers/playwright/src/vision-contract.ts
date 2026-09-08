import { createHash } from "node:crypto";
import { visionSchemas } from "./vision-contract.generated.js";
export type * from "./vision-contract.generated.js";

export class VisionWorkerError extends Error {
  readonly code: string;
  constructor(code: string) { super(code); this.code = code; }
}
export function requireVision(condition: unknown, code = "invalid_contract"): asserts condition {
  if (!condition) throw new VisionWorkerError(code);
}
export const uuid = (value: unknown): value is string => typeof value === "string" &&
  /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(value);
export const digest = (value: string | Buffer): string => createHash("sha256").update(value).digest("hex");
export const canonical = (value: unknown): string => {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.entries(value).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)
    .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`).join(",")}}`;
  return JSON.stringify(value);
};
export const stableCss = /^(?:[a-z][a-z0-9-]*)?\[(?:id|data-testid|name|aria-label|title)="[^"\\\r\n]+"\]$/;
export function safeLocatorValue(value: string): boolean {
  return value.length > 0 && value.length <= 240 && value === value.trim() && !/[\x00-\x1f]/.test(value) &&
    !/(\b(?:password|passwd|secret|token|api[_ -]?key|authorization|cookie)\b|[\w.+-]+@[\w.-]+\.[a-z]{2,}|\b\d{7,}\b|https?:\/\/|\[redacted\])/i.test(value);
}

type Schema = {
  $ref?: string; anyOf?: Schema[]; const?: unknown; enum?: unknown[]; type?: string;
  required?: string[]; properties?: Record<string, Schema>; additionalProperties?: boolean;
  default?: unknown; items?: Schema; minItems?: number; maxItems?: number;
  minLength?: number; maxLength?: number; pattern?: string; format?: string;
  minimum?: number; maximum?: number; exclusiveMinimum?: number;
};

// Schema shapes are generated from Python; semantic validators mirror Pydantic's
// model validators and are exercised against the very same accepted/rejected fixtures.
function parseSchema(schema: Schema, value: unknown): unknown {
  if (schema.$ref) return validateVision(schema.$ref.split("/").pop()!, value);
  if (schema.anyOf) {
    for (const child of schema.anyOf) { try { return parseSchema(child, value); } catch { /* next union arm */ } }
    throw new VisionWorkerError("invalid_contract");
  }
  if ("const" in schema) requireVision(value === schema.const);
  if (schema.enum) requireVision(schema.enum.includes(value));
  if (schema.type === "null") requireVision(value === null);
  if (schema.type === "boolean") requireVision(typeof value === "boolean");
  if (schema.type === "integer" || schema.type === "number") {
    requireVision(typeof value === "number" && Number.isFinite(value));
    if (schema.type === "integer") requireVision(Number.isSafeInteger(value));
    if (schema.minimum !== undefined) requireVision(value >= schema.minimum);
    if (schema.maximum !== undefined) requireVision(value <= schema.maximum);
    if (schema.exclusiveMinimum !== undefined) requireVision(value > schema.exclusiveMinimum);
  }
  if (schema.type === "string") {
    requireVision(typeof value === "string");
    const length = [...value].length;
    if (schema.minLength !== undefined) requireVision(length >= schema.minLength);
    if (schema.maxLength !== undefined) requireVision(length <= schema.maxLength);
    if (schema.pattern) requireVision(new RegExp(schema.pattern).test(value));
    if (schema.format === "uuid") { requireVision(uuid(value)); return value.toLowerCase(); }
    if (schema.format === "date-time") requireVision(Number.isFinite(Date.parse(value)));
  }
  if (schema.type === "array") {
    requireVision(Array.isArray(value));
    if (schema.minItems !== undefined) requireVision(value.length >= schema.minItems);
    if (schema.maxItems !== undefined) requireVision(value.length <= schema.maxItems);
    return value.map((item) => parseSchema(schema.items!, item));
  }
  if (schema.type === "object") {
    requireVision(value && typeof value === "object" && !Array.isArray(value));
    const input = value as Record<string, unknown>;
    const properties = schema.properties ?? {};
    requireVision((schema.required ?? []).every((key) => key in input));
    if (schema.additionalProperties === false) requireVision(Object.keys(input).every((key) => key in properties));
    const result: Record<string, unknown> = {};
    for (const [key, child] of Object.entries(properties)) {
      if (key in input) result[key] = parseSchema(child, input[key]);
      else if ("default" in child) result[key] = structuredClone(child.default);
    }
    return result;
  }
  return value;
}

export function validateVision<T = unknown>(name: string, input: unknown): T {
  requireVision(name in visionSchemas);
  const v = parseSchema(visionSchemas[name] as Schema, input) as Record<string, any>;
  if (name === "VisualLocatorScope") requireVision(safeLocatorValue(v.selector) && stableCss.test(v.selector));
  if (name === "VisualLocatorDescriptor") {
    requireVision(safeLocatorValue(v.value));
    requireVision((v.strategy === "role") === (v.role !== null));
    if (v.strategy === "css") requireVision(stableCss.test(v.value));
  }
  if (name === "VisualBoundingBox") requireVision(v.x + v.width <= 1.000001 && v.y + v.height <= 1.000001);
  if (name === "VisualLocatorEvidence") {
    if (v.status === "verified") requireVision(v.descriptor && v.bounding_box && v.matched_count === 1 &&
      v.target_match && v.actionable && v.verified_at && !v.reason_code);
    else requireVision(v.reason_code && !v.verified_at);
    if (v.status === "redacted") requireVision(!v.descriptor);
  }
  if (name === "VisualOperation") {
    const final = ["completed", "failed", "unknown", "rejected"].includes(v.status);
    requireVision(final === (v.ended_at !== null) && v.parent_operation_id !== v.id);
    if (final) requireVision(v.outcome_code && Date.parse(v.ended_at) >= Date.parse(v.started_at));
    if (["executing", "completed"].includes(v.status)) requireVision(v.actual_before_frame_id);
    for (const role of ["before", "after"]) {
      const frame = v[`actual_${role}_frame_id`], reason = v[`${role}_unavailable_reason`];
      requireVision(!(frame && reason));
      if (final) requireVision(frame || reason);
    }
  }
  if (name === "VisualHandoffBranch") {
    requireVision(new Set(v.steps.map((s: any) => s.operation_id)).size === v.steps.length);
    requireVision((v.status === "blocked") === (v.reason_code !== null));
    if (v.steps.some((s: any) => s.input_reference)) requireVision(v.status === "blocked" && v.reason_code === "input_binding_required");
  }
  if (name === "VisualLocatorHandoff") {
    requireVision(new Set(v.branches.map((b: any) => b.id)).size === v.branches.length);
    const { content_hash, ...payload } = v;
    requireVision(digest(canonical(payload)) === content_hash);
  }
  if (name === "VisualWorkerAction") {
    const required: Record<string, string[]> = { click: ["x", "y"], type: ["x", "y", "text"], scroll: ["delta_y"], wait: ["duration_ms"] };
    requireVision(["x", "y", "text", "delta_y", "duration_ms"].every((key) =>
      (v[key] !== null) === (required[v.kind] ?? []).includes(key)));
  }
  if (name === "VisualWorkerPrepare") {
    if (["click", "type"].includes(v.action.kind)) requireVision(v.state_id && v.proposal_id);
    requireVision((v.checkpoint_id === null) === (v.checkpoint_state_id === null));
    if (v.purpose === "replay") requireVision(v.replay_operation_id);
  }
  if (name === "VisualWorkerOperationResult") {
    const op = v.operation;
    requireVision(new Set(v.frames.map((frame: any) => frame.role)).size === v.frames.length);
    for (const item of [...v.frames, ...(v.locator ? [v.locator] : [])]) requireVision(
      item.tenant_id === op.tenant_id && item.project_id === op.project_id &&
      item.session_id === op.session_id && item.operation_id === op.id);
    for (const frame of v.frames) requireVision(frame.id === op[`actual_${frame.role}_frame_id`]);
    if (v.locator) requireVision(v.locator.id === op.locator_id && v.locator.originating_frame_id === op.actual_before_frame_id);
  }
  return v as T;
}

export function allowedOrigin(url: string, origins: string[]): boolean {
  try {
    const parsed = new URL(url);
    return ["http:", "https:"].includes(parsed.protocol) && !parsed.username && !parsed.password &&
      (origins.includes("*") || origins.includes(parsed.origin));
  } catch { return false; }
}
