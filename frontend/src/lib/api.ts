import axios, { AxiosError } from "axios";
import type {
  AgentConfigGrouped,
  AgentConfigResponse,
  AgentConfigResetResponse,
  AgentConfigSummary,
  AgentConfigUpdate,
  LLMProfileCreate,
  LLMProfileListResponse,
  LLMProfileResponse,
  LLMProfileUpdate,
  LLMTestRequest,
  LLMTestResponse,
  PaginationParams,
  PipelineRunListResponse,
  PipelineRunResponse,
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

  /** GET /api/v1/pipeline/runs */
  listRuns: async (
    params?: PaginationParams,
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
