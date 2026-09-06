import { createHash } from "node:crypto";
import ts from "typescript";

/**
 * Runtime validation for the v1 JSON boundary owned by packages/contracts.
 * Keep this deliberately dependency-free so a worker rejects malformed work
 * before opening a browser.
 */

export type JsonObject = Record<string, unknown>;

export type ExecutionRequestV1 = {
  contract_version: "v1";
  run_id: string;
  correlation_id: string;
  project_id: string;
  test_case_id: string;
  target_type: "web_ui" | "api" | "game";
  target_url?: string;
  revision: string;
  runner_config: JsonObject;
  artifact_policy: {
    trace_on_failure: boolean;
    video_on_failure: boolean;
    screenshot_on_failure: boolean;
    trace_on_success?: boolean;
    video_on_success?: boolean;
    screenshot_on_success?: boolean;
    retain_days: number;
  };
};

export type PlaywrightTestSourceMode = {
  mode: "playwright_test_source";
  playwright_test_source: string;
  source_hash: string;
  allowed_origins: string[];
};

export type ExecutionResultV1 = {
  contract_version: "v1";
  run_id: string;
  correlation_id: string;
  status: "passed" | "failed" | "errored" | "skipped";
  started_at: string;
  completed_at: string;
  summary: string;
  artifacts: Array<{ kind: string; uri: string; content_type?: string }>;
  runner_metadata: JsonObject;
};

const isObject = (value: unknown): value is JsonObject =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const hasExactKeys = (value: JsonObject, keys: string[]): boolean =>
  Object.keys(value).length === keys.length && keys.every((key) => key in value);
const isUuid = (value: unknown): value is string =>
  typeof value === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);

export function validateExecutionRequestV1(value: unknown): ExecutionRequestV1 {
  if (!isObject(value)) throw new Error("execution request must be an object");
  const policy = value.artifact_policy;
  if (
    value.contract_version !== "v1" ||
    !isUuid(value.run_id) ||
    !isUuid(value.correlation_id) ||
    !isUuid(value.project_id) ||
    typeof value.test_case_id !== "string" || value.test_case_id.length === 0 ||
    !["web_ui", "api", "game"].includes(String(value.target_type)) ||
    (value.target_url !== undefined && typeof value.target_url !== "string") ||
    typeof value.revision !== "string" || value.revision.length < 7 ||
    !isObject(value.runner_config) || !isObject(policy) ||
    typeof policy.trace_on_failure !== "boolean" ||
    typeof policy.video_on_failure !== "boolean" ||
    typeof policy.screenshot_on_failure !== "boolean" ||
    (policy.trace_on_success !== undefined && typeof policy.trace_on_success !== "boolean") ||
    (policy.video_on_success !== undefined && typeof policy.video_on_success !== "boolean") ||
    (policy.screenshot_on_success !== undefined && typeof policy.screenshot_on_success !== "boolean") ||
    typeof policy.retain_days !== "number" || !Number.isInteger(policy.retain_days) ||
    policy.retain_days < 1 || policy.retain_days > 3650
  ) throw new Error("invalid TestExecutionRequest v1");
  return value as ExecutionRequestV1;
}

export function validatePlaywrightTestSourceMode(value: unknown): PlaywrightTestSourceMode {
  if (!isObject(value) || !hasExactKeys(value, ["mode", "playwright_test_source", "source_hash", "allowed_origins"]) ||
    value.mode !== "playwright_test_source" ||
    typeof value.playwright_test_source !== "string" || value.playwright_test_source.length === 0 ||
    typeof value.source_hash !== "string" || !/^[a-f0-9]{64}$/.test(value.source_hash) ||
    !Array.isArray(value.allowed_origins) || value.allowed_origins.length === 0 ||
    !value.allowed_origins.every((origin) => origin === "*" || (typeof origin === "string" && (() => {
      try { const url = new URL(origin); return ["http:", "https:"].includes(url.protocol) && url.origin === origin; } catch { return false; }
    })())) ||
    createHash("sha256").update(value.playwright_test_source, "utf8").digest("hex") !== value.source_hash) {
    throw new Error("invalid playwright_test_source runner configuration");
  }
  assertAllowedGeneratedSource(value.playwright_test_source);
  return value as PlaywrightTestSourceMode;
}

export function assertAllowedGeneratedSource(source: string): void {
  const file = ts.createSourceFile("generated.spec.ts", source, ts.ScriptTarget.ES2022, true);
  const prohibited = new Set([
    "require", "eval", "Function", "fetch", "XMLHttpRequest", "WebSocket", "Worker",
    "process", "Buffer", "__dirname", "__filename", "child_process", "cluster", "dgram",
    "dns", "fs", "net", "tls", "vm", "worker_threads", "APIRequestContext",
  ]);
  let violation: string | undefined;
  const inspect = (node: ts.Node): void => {
    if (violation !== undefined) return;
    if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) {
      const module = node.moduleSpecifier;
      if (!module || !ts.isStringLiteral(module) || module.text !== "@playwright/test") {
        violation = "generated source may import only @playwright/test";
        return;
      }
    }
    if (ts.isCallExpression(node) && node.expression.kind === ts.SyntaxKind.ImportKeyword) {
      violation = "generated source may not use dynamic imports";
      return;
    }
    if (ts.isIdentifier(node) && prohibited.has(node.text)) {
      violation = `generated source uses prohibited API: ${node.text}`;
      return;
    }
    if (ts.isPropertyAssignment(node) && ts.isIdentifier(node.name) && node.name.text === "request") {
      violation = "generated source may not use direct network request APIs";
      return;
    }
    if (ts.isBindingElement(node) && ts.isIdentifier(node.name) && node.name.text === "request") {
      violation = "generated source may not use direct network request APIs";
      return;
    }
    ts.forEachChild(node, inspect);
  };
  inspect(file);
  const parseDiagnostics = (file as ts.SourceFile & { parseDiagnostics?: readonly ts.Diagnostic[] })
    .parseDiagnostics;
  if (parseDiagnostics !== undefined && parseDiagnostics.length > 0) {
    throw new Error("generated source is not valid TypeScript");
  }
  if (violation !== undefined) throw new Error(violation);
}

export function validateExecutionResultV1(value: unknown): ExecutionResultV1 {
  if (!isObject(value) || value.contract_version !== "v1" || !isUuid(value.run_id) ||
    !isUuid(value.correlation_id) || !["passed", "failed", "errored", "skipped"].includes(String(value.status)) ||
    typeof value.started_at !== "string" || typeof value.completed_at !== "string" ||
    typeof value.summary !== "string" || !Array.isArray(value.artifacts) || !isObject(value.runner_metadata)) {
    throw new Error("invalid TestExecutionResult v1");
  }
  for (const artifact of value.artifacts) {
    if (!isObject(artifact) || typeof artifact.kind !== "string" || typeof artifact.uri !== "string" ||
      (artifact.content_type !== undefined && typeof artifact.content_type !== "string")) {
      throw new Error("invalid TestExecutionResult v1 artifact");
    }
  }
  return value as ExecutionResultV1;
}
