import axios, { AxiosError } from "axios";
import type {
  AgentConfigByPipelineResponse,
  AgentConfigCreate,
  AgentConfigGroupedResponse,
  AgentConfigResponse,
  AgentConfigResetResponse,
  AgentConfigSummary,
  AgentConfigUpdate,
  DAGValidationResult,
  LLMProfileCreate,
  LLMProfileListResponse,
  LLMProfileResponse,
  LLMProfileUpdate,
  LLMTestRequest,
  LLMTestResponse,
  PaginationParams,
  PipelineActionResponse,
  PipelineAgentGroup,
  PipelineNodeResult,
  PipelineRunListResponse,
  PipelineRunResponse,
  PipelineNodeConfig,
  PipelineTemplate,
  PipelineTemplateCreate,
  PipelineTemplateListResponse,
  PipelineTemplateUpdate,
  StageConfig,
  StageConfigCreate,
  StageConfigUpdate,
  TemplateExportEnvelope,
} from "@/types";

// ─────────────────────────────────────────────────────────────────────────────
// Axios instance
// ─────────────────────────────────────────────────────────────────────────────

export const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 30_000,
});

// Request interceptor — inject JWT token
apiClient.interceptors.request.use((config) => {
  const token =
    typeof window !== "undefined"
      ? localStorage.getItem("auto_at_token")
      : null;
  if (token) {
    config.headers["Authorization"] = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor — unwrap data and normalise errors
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      // Token expired or invalid — clear stored credentials
      if (typeof window !== "undefined") {
        localStorage.removeItem("auto_at_token");
        localStorage.removeItem("auto_at_user");
        // Redirect to login (avoid full reload if already there)
        if (!window.location.pathname.startsWith("/login")) {
          window.location.href = "/login";
        }
      }
    }
    const message =
      (error.response?.data as { detail?: string })?.detail ??
      error.message ??
      "An unexpected error occurred.";
    return Promise.reject(new Error(String(message)));
  },
);

// ─────────────────────────────────────────────────────────────────────────────
// LLM Profiles
// ─────────────────────────────────────────────────────────────────────────────

export const llmProfilesApi = {
  /** GET /api/v1/admin/llm-profiles */
  list: async (params?: PaginationParams): Promise<LLMProfileListResponse> => {
    const { data } = await apiClient.get<LLMProfileListResponse>(
      "/api/v1/admin/llm-profiles",
      { params },
    );
    return data;
  },

  /** GET /api/v1/admin/llm-profiles/:id */
  get: async (id: string): Promise<LLMProfileResponse> => {
    const { data } = await apiClient.get<LLMProfileResponse>(
      `/api/v1/admin/llm-profiles/${id}`,
    );
    return data;
  },

  /** POST /api/v1/admin/llm-profiles */
  create: async (payload: LLMProfileCreate): Promise<LLMProfileResponse> => {
    const { data } = await apiClient.post<LLMProfileResponse>(
      "/api/v1/admin/llm-profiles",
      payload,
    );
    return data;
  },

  /** PUT /api/v1/admin/llm-profiles/:id */
  update: async (
    id: string,
    payload: LLMProfileUpdate,
  ): Promise<LLMProfileResponse> => {
    const { data } = await apiClient.put<LLMProfileResponse>(
      `/api/v1/admin/llm-profiles/${id}`,
      payload,
    );
    return data;
  },

  /** DELETE /api/v1/admin/llm-profiles/:id */
  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/api/v1/admin/llm-profiles/${id}`);
  },

  /** POST /api/v1/admin/llm-profiles/:id/set-default */
  setDefault: async (id: string): Promise<LLMProfileResponse> => {
    const { data } = await apiClient.post<LLMProfileResponse>(
      `/api/v1/admin/llm-profiles/${id}/set-default`,
    );
    return data;
  },

  /** POST /api/v1/admin/llm-profiles/:id/test */
  test: async (id: string, body?: LLMTestRequest): Promise<LLMTestResponse> => {
    const { data } = await apiClient.post<LLMTestResponse>(
      `/api/v1/admin/llm-profiles/${id}/test`,
      body ?? {},
    );
    return data;
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Agent Configs
// ─────────────────────────────────────────────────────────────────────────────

export const agentConfigsApi = {
  /**
   * GET /api/v1/admin/agent-configs?grouped=true
   * Returns agents grouped by stage.
   */
  listGrouped: async (): Promise<AgentConfigGroupedResponse> => {
    const { data } = await apiClient.get<AgentConfigGroupedResponse>(
      "/api/v1/admin/agent-configs",
      { params: { grouped: true } },
    );
    return data;
  },

  /**
   * GET /api/v1/admin/agent-configs
   * Returns flat list of all agent config summaries.
   */
  list: async (params?: {
    stage?: string;
    skip?: number;
    limit?: number;
  }): Promise<AgentConfigSummary[]> => {
    const { data } = await apiClient.get<AgentConfigSummary[]>(
      "/api/v1/admin/agent-configs",
      { params },
    );
    return data;
  },

  /** GET /api/v1/admin/agent-configs/:agent_id */
  get: async (agentId: string): Promise<AgentConfigResponse> => {
    const { data } = await apiClient.get<AgentConfigResponse>(
      `/api/v1/admin/agent-configs/${agentId}`,
    );
    return data;
  },

  /** PUT /api/v1/admin/agent-configs/:agent_id */
  update: async (
    agentId: string,
    payload: AgentConfigUpdate,
  ): Promise<AgentConfigResponse> => {
    const { data } = await apiClient.put<AgentConfigResponse>(
      `/api/v1/admin/agent-configs/${agentId}`,
      payload,
    );
    return data;
  },

  /** POST /api/v1/admin/agent-configs/:agent_id/reset */
  reset: async (agentId: string): Promise<AgentConfigResetResponse> => {
    const { data } = await apiClient.post<AgentConfigResetResponse>(
      `/api/v1/admin/agent-configs/${agentId}/reset`,
    );
    return data;
  },

  /** POST /api/v1/admin/agent-configs/reset-all */
  resetAll: async (): Promise<{ message: string; count: number }> => {
    const { data } = await apiClient.post<{ message: string; count: number }>(
      "/api/v1/admin/agent-configs/reset-all",
    );
    return data;
  },

  /** POST /api/v1/admin/agent-configs */
  create: async (payload: AgentConfigCreate): Promise<AgentConfigResponse> => {
    const { data } = await apiClient.post<AgentConfigResponse>(
      "/api/v1/admin/agent-configs",
      payload,
    );
    return data;
  },

  /** DELETE /api/v1/admin/agent-configs/:agent_id */
  delete: async (agentId: string): Promise<void> => {
    await apiClient.delete(`/api/v1/admin/agent-configs/${agentId}`);
  },

  /** GET /api/v1/admin/agent-configs/by-pipeline */
  listByPipeline: async (): Promise<AgentConfigByPipelineResponse> => {
    const { data } = await apiClient.get<AgentConfigByPipelineResponse>(
      "/api/v1/admin/agent-configs/by-pipeline",
    );
    return data;
  },

  /** GET /api/v1/admin/agent-configs/by-pipeline/:templateId */
  listByPipelineTemplate: async (
    templateId: string,
  ): Promise<PipelineAgentGroup> => {
    const { data } = await apiClient.get<PipelineAgentGroup>(
      `/api/v1/admin/agent-configs/by-pipeline/${templateId}`,
    );
    return data;
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Pipeline
// ─────────────────────────────────────────────────────────────────────────────

export const pipelineApi = {
  /**
   * POST /api/v1/pipeline/run
   * Upload a document file and start a pipeline run.
   */
  run: async (
    file: File,
    llmProfileId?: number | null,
  ): Promise<PipelineRunResponse> => {
    const form = new FormData();
    form.append("file", file);
    if (llmProfileId != null) {
      form.append("llm_profile_id", String(llmProfileId));
    }
    const { data } = await apiClient.post<PipelineRunResponse>(
      "/api/v1/pipeline/run",
      form,
      { headers: { "Content-Type": "multipart/form-data" }, timeout: 60_000 },
    );
    return data;
  },

  /**
   * POST /api/v1/pipeline/runs   (V3 — DAG runner)
   * Start a pipeline run based on a template. File is optional.
   */
  createRun: async (
    templateId: string,
    file?: File | null,
    llmProfileId?: number | null,
    runParams?: Record<string, unknown>,
  ): Promise<PipelineRunResponse> => {
    const form = new FormData();
    form.append("template_id", templateId);
    if (file) form.append("file", file);
    if (llmProfileId != null)
      form.append("llm_profile_id", String(llmProfileId));
    if (runParams) form.append("run_params", JSON.stringify(runParams));
    const { data } = await apiClient.post<PipelineRunResponse>(
      "/api/v1/pipeline/runs",
      form,
      { headers: { "Content-Type": "multipart/form-data" }, timeout: 60_000 },
    );
    return data;
  },

  /** GET /api/v1/pipeline/runs */
  listRuns: async (
    params?: PaginationParams & {
      template_id?: string;
      status?: string;
      page?: number;
      page_size?: number;
    },
  ): Promise<PipelineRunListResponse> => {
    const { data } = await apiClient.get<PipelineRunListResponse>(
      "/api/v1/pipeline/runs",
      { params },
    );
    return data;
  },

  /** GET /api/v1/pipeline/runs/:run_id */
  getRun: async (runId: string): Promise<PipelineRunResponse> => {
    const { data } = await apiClient.get<PipelineRunResponse>(
      `/api/v1/pipeline/runs/${runId}`,
    );
    return data;
  },

  /** DELETE /api/v1/pipeline/runs/:run_id */
  deleteRun: async (runId: string): Promise<void> => {
    await apiClient.delete(`/api/v1/pipeline/runs/${runId}`);
  },

  /** POST /api/v1/pipeline/runs/:run_id/cancel */
  cancelRun: async (runId: string): Promise<PipelineActionResponse> => {
    const { data } = await apiClient.post<PipelineActionResponse>(
      `/api/v1/pipeline/runs/${runId}/cancel`,
    );
    return data;
  },

  /** POST /api/v1/pipeline/runs/:run_id/pause */
  pauseRun: async (runId: string): Promise<PipelineActionResponse> => {
    const { data } = await apiClient.post<PipelineActionResponse>(
      `/api/v1/pipeline/runs/${runId}/pause`,
    );
    return data;
  },

  /** POST /api/v1/pipeline/runs/:run_id/resume */
  resumeRun: async (runId: string): Promise<PipelineActionResponse> => {
    const { data } = await apiClient.post<PipelineActionResponse>(
      `/api/v1/pipeline/runs/${runId}/resume`,
    );
    return data;
  },

  /** GET /api/v1/pipeline/runs/:run_id/export/html  (returns a URL for window.open) */
  getExportHtmlUrl: (runId: string): string => {
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    return `${base}/api/v1/pipeline/runs/${runId}/export/html`;
  },

  /** GET /api/v1/pipeline/runs/:run_id/export/docx  (returns a URL for window.open) */
  getExportDocxUrl: (runId: string): string => {
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    return `${base}/api/v1/pipeline/runs/${runId}/export/docx`;
  },

  /** GET /api/v1/pipeline/runs/:run_id/results */
  getRunResults: async (
    runId: string,
    params?: { stage?: string; agent_id?: string; node_id?: string },
  ): Promise<PipelineNodeResult[]> => {
    const { data } = await apiClient.get<PipelineNodeResult[]>(
      `/api/v1/pipeline/runs/${runId}/results`,
      params ? { params } : undefined,
    );
    return data;
  },

  /** GET /api/v1/pipeline/runs/:run_id/results/:node_id */
  getNodeResult: async (
    runId: string,
    nodeId: string,
  ): Promise<PipelineNodeResult> => {
    const { data } = await apiClient.get<PipelineNodeResult>(
      `/api/v1/pipeline/runs/${runId}/results/${nodeId}`,
    );
    return data;
  },

  /** GET /api/v1/pipeline/runs/:run_id/artifacts/playwright */
  listPlaywrightArtifacts: async (
    runId: string,
  ): Promise<Array<{ path: string; size_bytes: number }>> => {
    const { data } = await apiClient.get<Array<{ path: string; size_bytes: number }>>(
      `/api/v1/pipeline/runs/${runId}/artifacts/playwright`,
    );
    return data;
  },

  /** URL for downloading the playwright zip */
  getPlaywrightZipUrl: (runId: string): string => {
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    return `${base}/api/v1/pipeline/runs/${runId}/artifacts/playwright/zip`;
  },

  /** URL for downloading a single playwright artifact file */
  getPlaywrightFileUrl: (runId: string, filePath: string): string => {
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    return `${base}/api/v1/pipeline/runs/${runId}/artifacts/playwright/file?path=${encodeURIComponent(filePath)}`;
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Health
// ─────────────────────────────────────────────────────────────────────────────

export const healthApi = {
  check: async (): Promise<{
    status: string;
    version: string;
    env: string;
    database: string;
  }> => {
    const { data } = await apiClient.get("/health");
    return data;
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Chat
// ─────────────────────────────────────────────────────────────────────────────

export const chatApi = {
  /** GET /api/v1/chat/profiles */
  getProfiles: async (): Promise<import("@/types").ChatProfileItem[]> => {
    const { data } = await apiClient.get<import("@/types").ChatProfileItem[]>(
      "/api/v1/chat/profiles",
    );
    return data;
  },

  /**
   * POST /api/v1/chat/send – returns a ReadableStream (SSE).
   * Caller is responsible for consuming the stream.
   */
  sendStream: (
    messages: { role: string; content: string }[],
    llmProfileId?: string | null,
    systemPrompt?: string | null,
  ): Promise<Response> => {
    const baseURL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("auto_at_token")
        : null;
    return fetch(`${baseURL}/api/v1/chat/send`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        messages,
        llm_profile_id: llmProfileId ?? null,
        system_prompt: systemPrompt ?? null,
      }),
    });
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Auth & User management
// ─────────────────────────────────────────────────────────────────────────────

export interface UserResponse {
  username: string;
  full_name: string;
  role: "admin" | "qa" | "dev";
  is_active: boolean;
  created_at: string;
}

export interface UserCreateRequest {
  username: string;
  password: string;
  full_name?: string;
  role: "admin" | "qa" | "dev";
}

export interface UserUpdateRequest {
  full_name?: string;
  role?: "admin" | "qa" | "dev";
  is_active?: boolean;
  password?: string;
}

export const authApi = {
  /** GET /api/v1/auth/me */
  me: async (): Promise<UserResponse> => {
    const { data } = await apiClient.get<UserResponse>("/api/v1/auth/me");
    return data;
  },

  /** GET /api/v1/auth/users (admin only) */
  listUsers: async (): Promise<UserResponse[]> => {
    const { data } = await apiClient.get<UserResponse[]>("/api/v1/auth/users");
    return data;
  },

  /** POST /api/v1/auth/users (admin only) */
  createUser: async (payload: UserCreateRequest): Promise<UserResponse> => {
    const { data } = await apiClient.post<UserResponse>(
      "/api/v1/auth/users",
      payload,
    );
    return data;
  },

  /** PUT /api/v1/auth/users/:username (admin only) */
  updateUser: async (
    username: string,
    payload: UserUpdateRequest,
  ): Promise<UserResponse> => {
    const { data } = await apiClient.put<UserResponse>(
      `/api/v1/auth/users/${username}`,
      payload,
    );
    return data;
  },

  /** DELETE /api/v1/auth/users/:username (admin only) */
  deleteUser: async (username: string): Promise<void> => {
    await apiClient.delete(`/api/v1/auth/users/${username}`);
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Stage Configs
// ─────────────────────────────────────────────────────────────────────────────

export const stageConfigsApi = {
  /** GET /api/v1/admin/stage-configs */
  list: async (
    enabledOnly = false,
    templateId?: string,
    noFallback = false,
  ): Promise<StageConfig[]> => {
    const { data } = await apiClient.get<StageConfig[]>(
      "/api/v1/admin/stage-configs",
      {
        params: {
          ...(enabledOnly && { enabled_only: true }),
          ...(templateId && { template_id: templateId }),
          ...(noFallback && { no_fallback: true }),
        },
      },
    );
    return data;
  },

  /** GET /api/v1/admin/stage-configs/:stage_id */
  get: async (stageId: string): Promise<StageConfig> => {
    const { data } = await apiClient.get<StageConfig>(
      `/api/v1/admin/stage-configs/${stageId}`,
    );
    return data;
  },

  /** POST /api/v1/admin/stage-configs */
  create: async (payload: StageConfigCreate): Promise<StageConfig> => {
    const { data } = await apiClient.post<StageConfig>(
      "/api/v1/admin/stage-configs",
      payload,
    );
    return data;
  },

  /** PUT /api/v1/admin/stage-configs/:stage_id */
  update: async (
    stageId: string,
    payload: StageConfigUpdate,
  ): Promise<StageConfig> => {
    const { data } = await apiClient.put<StageConfig>(
      `/api/v1/admin/stage-configs/${stageId}`,
      payload,
    );
    return data;
  },

  /** DELETE /api/v1/admin/stage-configs/:stage_id */
  delete: async (stageId: string): Promise<void> => {
    await apiClient.delete(`/api/v1/admin/stage-configs/${stageId}`);
  },

  /** POST /api/v1/admin/stage-configs/reorder */
  reorder: async (stageIds: string[]): Promise<StageConfig[]> => {
    const { data } = await apiClient.post<StageConfig[]>(
      "/api/v1/admin/stage-configs/reorder",
      { stage_ids: stageIds },
    );
    return data;
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Pipeline Templates (V3)
// ─────────────────────────────────────────────────────────────────────────────

export const pipelineTemplatesApi = {
  /** GET /api/v1/pipeline-templates */
  list: async (params?: {
    page?: number;
    page_size?: number;
    include_archived?: boolean;
    tag?: string;
  }): Promise<PipelineTemplateListResponse> => {
    const { data } = await apiClient.get<PipelineTemplateListResponse>(
      "/api/v1/pipeline-templates",
      { params },
    );
    return data;
  },

  /** POST /api/v1/pipeline-templates */
  create: async (
    payload: PipelineTemplateCreate,
  ): Promise<PipelineTemplate> => {
    const { data } = await apiClient.post<PipelineTemplate>(
      "/api/v1/pipeline-templates",
      payload,
    );
    return data;
  },

  /** GET /api/v1/pipeline-templates/:template_id */
  get: async (templateId: string): Promise<PipelineTemplate> => {
    const { data } = await apiClient.get<PipelineTemplate>(
      `/api/v1/pipeline-templates/${templateId}`,
    );
    return data;
  },

  /** PUT /api/v1/pipeline-templates/:template_id */
  update: async (
    templateId: string,
    payload: PipelineTemplateUpdate,
  ): Promise<PipelineTemplate> => {
    const { data } = await apiClient.put<PipelineTemplate>(
      `/api/v1/pipeline-templates/${templateId}`,
      payload,
    );
    return data;
  },

  /** DELETE /api/v1/pipeline-templates/:template_id */
  delete: async (templateId: string): Promise<void> => {
    await apiClient.delete(`/api/v1/pipeline-templates/${templateId}`);
  },

  /** POST /api/v1/pipeline-templates/:template_id/clone */
  clone: async (
    templateId: string,
    newTemplateId: string,
    newName: string,
  ): Promise<PipelineTemplate> => {
    const { data } = await apiClient.post<PipelineTemplate>(
      `/api/v1/pipeline-templates/${templateId}/clone`,
      { new_template_id: newTemplateId, new_name: newName },
    );
    return data;
  },

  /** POST /api/v1/pipeline-templates/:template_id/archive */
  archive: async (templateId: string): Promise<PipelineTemplate> => {
    const { data } = await apiClient.post<PipelineTemplate>(
      `/api/v1/pipeline-templates/${templateId}/archive`,
    );
    return data;
  },

  /** POST /api/v1/pipeline-templates/:template_id/validate */
  validate: async (templateId: string): Promise<DAGValidationResult> => {
    const { data } = await apiClient.post<DAGValidationResult>(
      `/api/v1/pipeline-templates/${templateId}/validate`,
    );
    return data;
  },

  /** GET /api/v1/pipeline-templates/:template_id/export */
  exportTemplate: async (
    templateId: string,
  ): Promise<TemplateExportEnvelope> => {
    const { data } = await apiClient.get<TemplateExportEnvelope>(
      `/api/v1/pipeline-templates/${templateId}/export`,
    );
    return data;
  },

  /** POST /api/v1/pipeline-templates/import */
  importTemplate: async (
    templateData: PipelineTemplate,
  ): Promise<PipelineTemplate> => {
    const envelope = {
      auto_at_version: "3.0",
      export_type: "pipeline_template",
      template: templateData,
    };
    const { data } = await apiClient.post<PipelineTemplate>(
      "/api/v1/pipeline-templates/import",
      envelope,
    );
    return data;
  },

  /** PATCH /api/v1/pipeline-templates/{template_id}/node-stage */
  updateNodeStage: async (
    templateId: string,
    nodeId: string,
    stageId: string | null,
  ): Promise<{
    ok: boolean;
    template_id: string;
    node_id: string;
    stage_id: string | null;
  }> => {
    const { data } = await apiClient.patch(
      `/api/v1/pipeline-templates/${templateId}/node-stage`,
      { node_id: nodeId, stage_id: stageId },
    );
    return data;
  },

  /** POST /api/v1/pipeline-templates/:templateId/nodes — append one node without DAG validation */
  appendNode: async (
    templateId: string,
    node: PipelineNodeConfig,
  ): Promise<PipelineTemplate> => {
    const { data } = await apiClient.post<PipelineTemplate>(
      `/api/v1/pipeline-templates/${templateId}/nodes`,
      node,
    );
    return data;
  },
};
