import { AsyncLocalStorage } from "node:async_hooks";
import { errors } from "@playwright/test";
import { logEvent, type LogContext } from "./observability.js";
import { VisionWorkerError } from "./vision-contract.js";

export type VisionLogScope = { context: LogContext; fields: Record<string, unknown> };
export const visionLogScope = new AsyncLocalStorage<VisionLogScope>();

export function logVisionEvent(...args: Parameters<typeof logEvent>): void {
  try { logEvent(...args); } catch { /* Logging must not change browser outcomes. */ }
}

// Exception messages can contain page text, locators, URLs and credentials.
// Inspect them only to select a fixed category; never serialize them or stacks.
export function visionErrorType(error: unknown): string {
  if (error instanceof VisionWorkerError) return "contract_rejection";
  if (error instanceof errors.TimeoutError) return "timeout";
  if (error instanceof SyntaxError) return "invalid_json";
  if (error instanceof Error) {
    if (/target.*closed|page.*closed|browser.*closed|context.*closed/i.test(error.message)) return "target_closed";
    if (/protocol error/i.test(error.message)) return "browser_protocol_error";
  }
  return "unexpected_error";
}

export function logVisionFailure(event: string, fields: Record<string, unknown>): void {
  const scope = visionLogScope.getStore();
  logVisionEvent("warn", event, "Vision browser capture failed.", scope?.context, { ...scope?.fields, ...fields });
}

export function logVisionDiagnostic(event: string, message: string, fields: Record<string, unknown>): void {
  const scope = visionLogScope.getStore();
  logVisionEvent("error", event, message, scope?.context, { ...scope?.fields, ...fields });
}
