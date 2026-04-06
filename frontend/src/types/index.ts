// ─────────────────────────────────────────────────────────────────────────────
// LLM Provider
// ─────────────────────────────────────────────────────────────────────────────

export enum LLMProvider {
  OPENAI = "openai",
  ANTHROPIC = "anthropic",
  OLLAMA = "ollama",
  HUGGINGFACE = "huggingface",
  AZURE = "azure_openai",
  GROQ = "groq",
}

export const LLM_PROVIDER_LABELS: Record<LLMProvider, string> = {
  [LLMProvider.OPENAI]: "OpenAI",
  [LLMProvider.ANTHROPIC]: "Anthropic",
  [LLMProvider.OLLAMA]: "Ollama (Local)",
  [LLMProvider.HUGGINGFACE]: "HuggingFace",
  [LLMProvider.AZURE]: "Azure OpenAI",
  [LLMProvider.GROQ]: "Groq",
};

/** Providers that require an API key */
export const PROVIDERS_REQUIRING_API_KEY: LLMProvider[] = [
  LLMProvider.OPENAI,
  LLMProvider.ANTHROPIC,
  LLMProvider.HUGGINGFACE,
  LLMProvider.AZURE,
  LLMProvider.GROQ,
];

/** Providers that require a base URL */
export const PROVIDERS_REQUIRING_BASE_URL: LLMProvider[] = [
  LLMProvider.OLLAMA,
  LLMProvider.AZURE,
];

/** Common model suggestions per provider */
export const PROVIDER_MODELS: Record<LLMProvider, string[]> = {
  [LLMProvider.OPENAI]: [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-3.5-turbo",
  ],
  [LLMProvider.ANTHROPIC]: [
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
  ],
  [LLMProvider.OLLAMA]: [
    "llama3.2",
    "llama3.1",
    "granite3.1-dense",
    "mistral",
    "qwen2.5",
  ],
  [LLMProvider.HUGGINGFACE]: ["meta-llama/Llama-3.1-8B-Instruct"],
  [LLMProvider.AZURE]: ["gpt-4o", "gpt-4-turbo"],
  [LLMProvider.GROQ]: [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
  ],
};

// ─────────────────────────────────────────────────────────────────────────────
// LLM Profile
// ─────────────────────────────────────────────────────────────────────────────

export interface LLMProfileResponse {
  id: number;
  name: string;
  provider: LLMProvider;
  model: string;
  /** Masked API key, e.g. "••••••••abcd". Null if no key configured. */
  api_key: string | null;
  base_url: string | null;
  temperature: number;
  max_tokens: number;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface LLMProfileCreate {
  name: string;
  provider: LLMProvider;
  model: string;
  api_key?: string | null;
  base_url?: string | null;
  temperature: number;
  max_tokens: number;
  is_default: boolean;
}

export interface LLMProfileUpdate {
  name?: string;
  provider?: LLMProvider;
  model?: string;
  api_key?: string | null;
  base_url?: string | null;
  temperature?: number;
  max_tokens?: number;
  is_default?: boolean;
}

export interface LLMProfileListResponse {
  items: LLMProfileResponse[];
  total: number;
}

export interface LLMTestRequest {
  prompt?: string;
  timeout_seconds?: number;
}

export interface LLMTestResponse {
  success: boolean;
  message: string;
  response_preview?: string | null;
  latency_ms?: number | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Agent Config
// ─────────────────────────────────────────────────────────────────────────────

export type AgentStage = "ingestion" | "testcase" | "execution" | "reporting";

export const STAGE_LABELS: Record<AgentStage, string> = {
  ingestion: "Stage 1 – Ingestion & Analysis",
  testcase: "Stage 2 – Test Case Generation",
  execution: "Stage 3 – Execution",
  reporting: "Stage 4 – Reporting",
};

export const STAGE_ORDER: AgentStage[] = [
  "ingestion",
  "testcase",
  "execution",
  "reporting",
];

export interface AgentConfigSummary {
  id: number;
  agent_id: string;
  display_name: string;
  stage: AgentStage;
  llm_profile_id: number | null;
  llm_profile_name: string | null;
  enabled: boolean;
  verbose: boolean;
  max_iter: number;
  is_custom: boolean;
  updated_at: string;
}

export interface AgentConfigResponse {
  id: number;
  agent_id: string;
  display_name: string;
  stage: AgentStage;
  role: string;
  goal: string;
  backstory: string;
  llm_profile_id: number | null;
  llm_profile: LLMProfileResponse | null;
  enabled: boolean;
  verbose: boolean;
  max_iter: number;
  created_at: string;
  updated_at: string;
}

export interface AgentConfigGrouped {
  ingestion: AgentConfigSummary[];
  testcase: AgentConfigSummary[];
  execution: AgentConfigSummary[];
  reporting: AgentConfigSummary[];
}

export interface AgentConfigUpdate {
  display_name?: string;
  stage?: AgentStage;
  role?: string;
  goal?: string;
  backstory?: string;
  llm_profile_id?: number | null;
  enabled?: boolean;
  verbose?: boolean;
  max_iter?: number;
}

export interface AgentConfigResetResponse {
  agent_id: string;
  message: string;
  config: AgentConfigResponse;
}

// ─────────────────────────────────────────────────────────────────────────────
// Pipeline
// ─────────────────────────────────────────────────────────────────────────────

export type PipelineStatus =
  | "pending"
  | "running"
  | "paused"
  | "completed"
  | "failed"
  | "cancelled";

export type AgentRunStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "skipped";

export interface PipelineRunCreate {
  llm_profile_id?: number | null;
}

export interface AgentRunResult {
  agent_id: string;
  display_name: string;
  stage: AgentStage;
  status: AgentRunStatus;
  output_preview?: string | null;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface PipelineRunResponse {
  id: string;
  status: PipelineStatus;
  llm_profile_id?: number | null;
  document_filename: string;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  error_message?: string | null;
  agent_runs: AgentRunResult[];
  // V3 DAG fields
  run_id?: string;
  template_id?: string | null;
  current_node?: string | null;
  completed_nodes?: string[];
  failed_nodes?: string[];
  node_statuses?: Record<string, string>;
  execution_layers?: string[][];
  duration_seconds?: number | null;
  current_stage?: string | null;
  completed_stages?: string[];
  paused_at?: string | null;
  resumed_at?: string | null;
}

export interface PipelineRunListResponse {
  items: PipelineRunResponse[];
  total: number;
  page?: number;
  page_size?: number;
}

// Per-node result (V3)
export interface PipelineNodeResult {
  run_id: string;
  node_id: string;
  node_type: string;
  label: string;
  output?: unknown;
  output_preview?: string | null;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  duration_seconds?: number | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// WebSocket Events
// ─────────────────────────────────────────────────────────────────────────────

export type WSEventType =
  | "connected"
  | "ping"
  | "pong"
  | "run.started"
  | "stage.started"
  | "agent.started"
  | "agent.progress"
  | "agent.completed"
  | "agent.failed"
  | "stage.completed"
  | "run.completed"
  | "run.failed"
  | "run.paused"
  | "run.resumed"
  | "run.cancelled"
  | "layer.started"
  | "layer.completed"
  | "node.started"
  | "node.completed"
  | "node.failed"
  | "node.skipped"
  | "node.progress"
  | "log";

export interface WSEvent {
  event: WSEventType;
  run_id: string;
  timestamp: string;
  data: Record<string, unknown>;
}

// ─────────────────────────────────────────────────────────────────────────────
// Generic API helpers
// ─────────────────────────────────────────────────────────────────────────────

export interface ApiError {
  detail: string | { msg: string; type: string }[];
}

export interface PaginationParams {
  skip?: number;
  limit?: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Chat
// ─────────────────────────────────────────────────────────────────────────────

export type ChatRole = "user" | "assistant" | "system";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  timestamp: Date;
  streaming?: boolean;
}

export interface ChatRequest {
  messages: { role: ChatRole; content: string }[];
  llm_profile_id?: number | null;
  system_prompt?: string | null;
}

export interface ChatProfileItem {
  id: number;
  name: string;
  provider: string;
  model: string;
  is_default: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// Stage Config
// ─────────────────────────────────────────────────────────────────────────────

export type StageCrewType =
  | "pure_python"
  | "crewai_sequential"
  | "crewai_hierarchical";

export const CREW_TYPE_LABELS: Record<StageCrewType, string> = {
  pure_python: "Pure Python",
  crewai_sequential: "CrewAI Sequential",
  crewai_hierarchical: "CrewAI Hierarchical",
};

export interface StageConfig {
  stage_id: string;
  display_name: string;
  description: string;
  order: number;
  enabled: boolean;
  crew_type: StageCrewType;
  timeout_seconds: number;
  is_builtin: boolean;
  created_at: string;
  updated_at: string;
}

export interface StageConfigCreate {
  stage_id: string;
  display_name: string;
  description?: string;
  order: number;
  enabled: boolean;
  crew_type: StageCrewType;
  timeout_seconds: number;
}

export interface StageConfigUpdate {
  display_name?: string;
  description?: string;
  order?: number;
  enabled?: boolean;
  crew_type?: StageCrewType;
  timeout_seconds?: number;
}

export interface StageReorderRequest {
  stages: { stage_id: string; order: number }[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Agent Config (extended for V2)
// ─────────────────────────────────────────────────────────────────────────────

export interface AgentConfigCreate {
  agent_id: string;
  display_name: string;
  stage: string;
  role: string;
  goal: string;
  backstory: string;
  llm_profile_id?: number | null;
  enabled?: boolean;
  verbose?: boolean;
  max_iter?: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Pipeline Template (V3)
// ─────────────────────────────────────────────────────────────────────────────

export type NodeType = "input" | "output" | "agent" | "pure_python";

export interface PipelineNodeConfig {
  node_id: string;
  node_type: NodeType;
  agent_id?: string;
  label: string;
  description: string;
  position_x: number;
  position_y: number;
  timeout_seconds: number;
  retry_count: number;
  enabled: boolean;
  config_overrides: Record<string, unknown>;
}

export interface PipelineEdgeConfig {
  edge_id: string;
  source_node_id: string;
  target_node_id: string;
  source_handle?: string;
  target_handle?: string;
  label?: string;
  animated: boolean;
}

export interface PipelineTemplate {
  id: string;
  template_id: string;
  name: string;
  description: string;
  version: number;
  nodes: PipelineNodeConfig[];
  edges: PipelineEdgeConfig[];
  is_builtin: boolean;
  is_archived: boolean;
  tags: string[];
  node_count: number;
  edge_count: number;
  created_at: string;
  updated_at: string;
}

export interface PipelineTemplateListItem {
  id: string;
  template_id: string;
  name: string;
  description: string;
  version: number;
  is_builtin: boolean;
  is_archived: boolean;
  tags: string[];
  node_count: number;
  edge_count: number;
  last_run_at?: string;
  last_run_status?: string;
  created_at: string;
  updated_at: string;
}

export interface PipelineTemplateCreate {
  template_id: string;
  name: string;
  description?: string;
  nodes?: PipelineNodeConfig[];
  edges?: PipelineEdgeConfig[];
  tags?: string[];
}

export interface PipelineTemplateUpdate {
  name?: string;
  description?: string;
  nodes?: PipelineNodeConfig[];
  edges?: PipelineEdgeConfig[];
  tags?: string[];
}

export interface DAGValidationResult {
  is_valid: boolean;
  errors: string[];
  warnings: string[];
  execution_layers: string[][];
  total_layers: number;
  total_nodes: number;
  estimated_parallel_speedup?: number;
}

export interface PipelineTemplateListResponse {
  items: PipelineTemplateListItem[];
  total: number;
}
