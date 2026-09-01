type SafeValue = string | number | boolean | null | SafeValue[] | { [key: string]: SafeValue };

export type LogContext = { correlation_id?: string; trace_id?: string; span_id?: string; run_id?: string; attempt?: number };

const sensitiveKey = /authorization|cookie|token|secret|password|api[_-]?key|credential/i;
const credential = /\b(?:bearer|basic)\s+[a-z0-9._~+/-]+=*/gi;
const querySecret = /([?&](?:token|secret|password|api[_-]?key|authorization)=)[^&#\s]*/gi;
export const RUNNER_LOG_MAX_BYTES = 64 * 1024;

function redact(value: unknown, key?: string): SafeValue {
  if (key && sensitiveKey.test(key)) return "[REDACTED]";
  if (typeof value === "string") return value.replace(credential, "[REDACTED]").replace(querySecret, "$1[REDACTED]");
  if (typeof value === "number" || typeof value === "boolean" || value === null) return value;
  if (Array.isArray(value)) return value.map((item) => redact(item));
  if (typeof value === "object" && value !== null) return Object.fromEntries(Object.entries(value).map(([itemKey, itemValue]) => [itemKey, redact(itemValue, itemKey)]));
  return "[REDACTED]";
}

export function traceContext(traceparent?: unknown): Pick<LogContext, "trace_id" | "span_id"> {
  if (typeof traceparent !== "string") return {};
  const match = /^00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$/i.exec(traceparent);
  return match ? { trace_id: match[1].toLowerCase(), span_id: match[2].toLowerCase() } : {};
}

export function executionContext(payload: unknown): LogContext {
  if (typeof payload !== "object" || payload === null) return {};
  const record = payload as Record<string, unknown>;
  const config = typeof record.runner_config === "object" && record.runner_config !== null ? record.runner_config as Record<string, unknown> : {};
  return { ...(typeof record.run_id === "string" ? { run_id: record.run_id } : {}), ...(typeof record.correlation_id === "string" ? { correlation_id: record.correlation_id } : {}), ...traceContext(record.traceparent ?? config.traceparent) };
}

export function logEvent(level: "info" | "warn" | "error", event: string, message: string, context: LogContext = {}, fields: Record<string, unknown> = {}): void {
  const safeContext = redact(context) as Record<string, SafeValue>;
  const safeFields = redact(fields) as Record<string, SafeValue>;
  const line = JSON.stringify({ timestamp: new Date().toISOString(), level, service: process.env.LOG_SERVICE_NAME ?? "auto-at-playwright-worker", environment: process.env.ENVIRONMENT ?? "local", event, message: redact(message), ...safeContext, ...safeFields });
  console[level === "warn" ? "warn" : level === "error" ? "error" : "log"](line);
}

/** Bounded, redacted execution evidence; failures never affect a run verdict. */
export class RunnerEventSink {
  private readonly lines: string[] = [];
  private bytes = 0;
  private truncated = false;
  private readonly context: LogContext;
  private readonly maxBytes: number;

  constructor(context: LogContext, maxBytes = RUNNER_LOG_MAX_BYTES) {
    this.context = context;
    this.maxBytes = maxBytes;
  }

  record(event: string, message: string, fields: Record<string, unknown> = {}): void {
    if (this.truncated) return;
    try {
      const line = JSON.stringify({ timestamp: new Date().toISOString(), event, message: redact(message), ...redact(this.context) as Record<string, SafeValue>, ...redact(fields) as Record<string, SafeValue> });
      const lineBytes = Buffer.byteLength(`${line}\n`);
      if (this.bytes + lineBytes > this.maxBytes) {
        this.truncated = true;
        const truncation = JSON.stringify({ timestamp: new Date().toISOString(), event: "runner.log.truncated", message: "Runner log reached its byte limit." });
        this.lines.push(truncation);
        return;
      }
      this.lines.push(line);
      this.bytes += lineBytes;
    } catch {
      // Observability must never change the deterministic result.
    }
  }

  serialize(): string { return this.lines.length === 0 ? "" : `${this.lines.join("\n")}\n`; }
}

export { redact };
