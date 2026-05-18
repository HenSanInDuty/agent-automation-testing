export const SHARED_VERSION = "0.1.0";

// Types
export * from "./types";

// API client
export * from "./api/client";

// Auth
export * from "./auth/auth-context";
export * from "./auth/AuthGuard";

// Lib
export * from "./lib/queryClient";
export * from "./lib/utils";
export * from "./lib/wsManager";

// Hooks
export * from "./hooks/usePipeline";
export * from "./hooks/usePipelineTemplates";
export * from "./hooks/usePipelineWebSocket";
export * from "./hooks/useLLMProfiles";

// Store
export * from "./store/pipelineStore";

// UI components
export * from "./components/ui/Button";
export * from "./components/ui/Toast";
export * from "./components/ui/Modal";
export * from "./components/ui/Input";
export * from "./components/ui/Select";
export * from "./components/ui/Skeleton";
export * from "./components/ui/ErrorBoundary";

// Pipeline components
export * from "./components/pipeline/DocumentUpload";
export * from "./components/pipeline/LLMProfileSelector";
export * from "./components/pipeline/PipelineControls";
export * from "./components/pipeline/PipelineProgress";
export * from "./components/pipeline/PipelineRunDetailPage";
export * from "./components/pipeline/PipelineRunHistoryPage";
export * from "./components/pipeline/PipelineRunPage";
export * from "./components/pipeline/PrettyOutput";
export * from "./components/pipeline/ResultsViewer";
export * from "./components/pipeline/RunHistory";
export * from "./components/pipeline/StageResultsPanel";

// Pipelines components
export * from "./components/pipelines/PipelineTemplateCard";
