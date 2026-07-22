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
    retain_days: number;
  };
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
    typeof policy.retain_days !== "number" || !Number.isInteger(policy.retain_days) ||
    policy.retain_days < 1 || policy.retain_days > 3650
  ) throw new Error("invalid TestExecutionRequest v1");
  return value as ExecutionRequestV1;
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
