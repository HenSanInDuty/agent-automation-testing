import axios, { AxiosError } from "axios";
import type {
  AgentConfigCreate,
  AgentConfigGrouped,
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
  PipelineNodeResult,
  PipelineRunListResponse,
  PipelineRunResponse,
  PipelineTemplate,
  PipelineTemplateCreate,
  PipelineTemplateListResponse,
  PipelineTemplateUpdate,
  StageConfig,
  StageConfigCreate,
  StageConfigUpdate,
  StageReorderRequest,
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

// Response interceptor — unwrap data and normalise errors
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
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
  get: async (id: number): Promise<LLMProfileResponse> => {
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
    id: number,
    payload: LLMProfileUpdate,
  ): Promise<LLMProfileResponse> => {
    const { data } = await apiClient.put<LLMProfileResponse>(
      `/api/v1/admin/llm-profiles/${id}`,
      payload,
    );
    return data;
  },

  /** DELETE /api/v1/admin/llm-profiles/:id */
  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`/api/v1/admin/llm-profiles/${id}`);
  },

  /** POST /api/v1/admin/llm-profiles/:id/set-default */
  setDefault: async (id: number): Promise<LLMProfileResponse> => {
    const { data } = await apiClient.post<LLMProfileResponse>(
      `/api/v1/admin/llm-profiles/${id}/set-default`,
    );
    return data;
  },

  /** POST /api/v1/admin/llm-profiles/:id/test */
  test: async (id: number, body?: LLMTestRequest): Promise<LLMTestResponse> => {
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
  listGrouped: async (): Promise<AgentConfigGrouped> => {
    const { data } = await apiClient.get<AgentConfigGrouped>(
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
  delete: async (agentId: string): Promise<{ deleted: string }> => {
    const { data } = await apiClient.delete<{ deleted: string }>(
      `/api/v1/admin/agent-configs/${agentId}`,
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
  cancelRun: async (runId: string): Promise<PipelineRunResponse> => {
    const { data } = await apiClient.post<PipelineRunResponse>(
      `/api/v1/pipeline/runs/${runId}/cancel`,
    );
    return data;
  },

  /** POST /api/v1/pipeline/runs/:run_id/pause */
  pauseRun: async (
    runId: string,
  ): Promise<{ status: string; run_id: string; message?: string }> => {
    const { data } = await apiClient.post<{
      status: string;
      run_id: string;
      message?: string;
    }>(`/api/v1/pipeline/runs/${runId}/pause`);
    return data;
  },

  /** POST /api/v1/pipeline/runs/:run_id/resume */
  resumeRun: async (
    runId: string,
  ): Promise<{ status: string; run_id: string }> => {
    const { data } = await apiClient.post<{ status: string; run_id: string }>(
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

  /** GET /api/v1/pipeline/runs/:run_id/results?stage=xxx */
  getStageResults: async (
    runId: string,
    stage?: string,
  ): Promise<Record<string, unknown>> => {
    const { data } = await apiClient.get<Record<string, unknown>>(
      `/api/v1/pipeline/runs/${runId}/results`,
      stage ? { params: { stage } } : undefined,
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
    llmProfileId?: number | null,
    systemPrompt?: string | null,
  ): Promise<Response> => {
    const baseURL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    return fetch(`${baseURL}/api/v1/chat/send`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages,
        llm_profile_id: llmProfileId ?? null,
        system_prompt: systemPrompt ?? null,
      }),
    });
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Stage Configs
// ─────────────────────────────────────────────────────────────────────────────

export const stageConfigsApi = {
  /** GET /api/v1/admin/stage-configs */
  list: async (): Promise<StageConfig[]> => {
    const { data } = await apiClient.get<StageConfig[]>(
      "/api/v1/admin/stage-configs",
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
  delete: async (stageId: string): Promise<{ deleted: string }> => {
    const { data } = await apiClient.delete<{ deleted: string }>(
      `/api/v1/admin/stage-configs/${stageId}`,
    );
    return data;
  },

  /** POST /api/v1/admin/stage-configs/reorder */
  reorder: async (payload: StageReorderRequest): Promise<StageConfig[]> => {
    const { data } = await apiClient.post<StageConfig[]>(
      "/api/v1/admin/stage-configs/reorder",
      payload,
    );
    return data;
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Pipeline Templates (V3)
// ─────────────────────────────────────────────────────────────────────────────

export const pipelineTemplatesApi = {
  /** GET /api/v1/pipeline/templates */
  list: async (params?: {
    skip?: number;
    limit?: number;
    include_archived?: boolean;
    tag?: string;
  }): Promise<PipelineTemplateListResponse> => {
    const { data } = await apiClient.get<PipelineTemplateListResponse>(
      "/api/v1/pipeline/templates",
      { params },
    );
    return data;
  },

  /** POST /api/v1/pipeline/templates */
  create: async (
    payload: PipelineTemplateCreate,
  ): Promise<PipelineTemplate> => {
    const { data } = await apiClient.post<PipelineTemplate>(
      "/api/v1/pipeline/templates",
      payload,
    );
    return data;
  },

  /** GET /api/v1/pipeline/templates/:template_id */
  get: async (templateId: string): Promise<PipelineTemplate> => {
    const { data } = await apiClient.get<PipelineTemplate>(
      `/api/v1/pipeline/templates/${templateId}`,
    );
    return data;
  },

  /** PUT /api/v1/pipeline/templates/:template_id */
  update: async (
    templateId: string,
    payload: PipelineTemplateUpdate,
  ): Promise<PipelineTemplate> => {
    const { data } = await apiClient.put<PipelineTemplate>(
      `/api/v1/pipeline/templates/${templateId}`,
      payload,
    );
    return data;
  },

  /** DELETE /api/v1/pipeline/templates/:template_id */
  delete: async (templateId: string): Promise<void> => {
    await apiClient.delete(`/api/v1/pipeline/templates/${templateId}`);
  },

  /** POST /api/v1/pipeline/templates/:template_id/clone */
  clone: async (
    templateId: string,
    newName?: string,
  ): Promise<PipelineTemplate> => {
    const { data } = await apiClient.post<PipelineTemplate>(
      `/api/v1/pipeline/templates/${templateId}/clone`,
      newName ? { name: newName } : {},
    );
    return data;
  },

  /** POST /api/v1/pipeline/templates/:template_id/archive */
  archive: async (templateId: string): Promise<PipelineTemplate> => {
    const { data } = await apiClient.post<PipelineTemplate>(
      `/api/v1/pipeline/templates/${templateId}/archive`,
    );
    return data;
  },

  /** POST /api/v1/pipeline/templates/:template_id/validate */
  validate: async (templateId: string): Promise<DAGValidationResult> => {
    const { data } = await apiClient.post<DAGValidationResult>(
      `/api/v1/pipeline/templates/${templateId}/validate`,
    );
    return data;
  },

  /** GET /api/v1/pipeline/templates/:template_id/export */
  exportTemplate: async (templateId: string): Promise<PipelineTemplate> => {
    const { data } = await apiClient.get<PipelineTemplate>(
      `/api/v1/pipeline/templates/${templateId}/export`,
    );
    return data;
  },

  /** POST /api/v1/pipeline/templates/import */
  importTemplate: async (
    templateData: PipelineTemplate,
  ): Promise<PipelineTemplate> => {
    const { data } = await apiClient.post<PipelineTemplate>(
      "/api/v1/pipeline/templates/import",
      templateData,
    );
    return data;
  },
};
