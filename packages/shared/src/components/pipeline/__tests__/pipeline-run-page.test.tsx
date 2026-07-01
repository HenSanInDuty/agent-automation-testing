import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PipelineRunPage } from "../PipelineRunPage";

const startMutation = {
  isPending: false,
  mutateAsync: vi.fn(),
};

const cancelMutation = {
  isPending: false,
  mutateAsync: vi.fn(),
};

vi.mock("next/link", () => ({
  default: ({ children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a {...props}>{children}</a>
  ),
}));

vi.mock("@tanstack/react-query", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@tanstack/react-query")>()),
  useQuery: () => ({ data: undefined }),
}));

vi.mock("../../../hooks/usePipelineTemplates", () => ({
  usePipelineTemplate: (templateId: string) => ({
    data: { id: templateId, name: templateId, nodes: [] },
    isLoading: false,
    error: null,
  }),
}));

vi.mock("../../../hooks/usePipeline", () => ({
  usePipelineRun: () => ({ data: undefined }),
  useStartDagPipeline: () => startMutation,
  useCancelPipeline: () => cancelMutation,
}));

const DEFAULT_STORE_STATE = {
  activeRunId: null as string | null,
  activeRunStatus: null as string | null,
  nodeStatuses: {} as Record<string, string>,
  isTerminal: false,
  wsStatus: "disconnected",
  logMessages: [] as string[],
  activeTemplateId: null as string | null,
  startSession: vi.fn(),
  clearSession: vi.fn(),
  syncRunStatus: vi.fn(),
  connectWebSocket: vi.fn(),
};

let storeState = { ...DEFAULT_STORE_STATE };

vi.mock("../../../store/pipelineStore", () => ({
  usePipelineStore: (selector: (state: typeof storeState) => unknown) =>
    selector(storeState),
}));

describe("PipelineRunPage document requirements", () => {
  beforeEach(() => {
    startMutation.mutateAsync.mockReset();
    cancelMutation.mutateAsync.mockReset();
    storeState = { ...DEFAULT_STORE_STATE, clearSession: vi.fn() };
  });

  it("blocks automation-testing-api runs until a Markdown spec is selected", () => {
    render(<PipelineRunPage templateId="automation-testing-api" hideLlmProfile />);

    expect(screen.getByRole("button", { name: "Run Pipeline" })).toBeDisabled();
    expect(
      screen.getByText("Upload one Markdown API specification before starting the pipeline."),
    ).toBeInTheDocument();
    expect(document.querySelector('input[type="file"]')).toHaveAttribute(
      "accept",
      ".md,.markdown,.pdf,.docx,.txt,.csv,.xlsx,.xls",
    );
  });

  it("keeps document uploads optional for other templates", () => {
    render(<PipelineRunPage templateId="general-pipeline" hideLlmProfile />);

    expect(screen.getByRole("button", { name: "Run Pipeline" })).toBeEnabled();
    expect(screen.getByText("Optional input file")).toBeInTheDocument();
  });

  it("offers an enabled 'New run' reset after a terminal run with no document in hand", () => {
    // Simulate landing back on /run after completion: the store still reports a
    // terminal run but the uploaded file is gone from local state.
    storeState.activeRunId = "run-123";
    storeState.activeRunStatus = "completed";
    storeState.isTerminal = true;
    storeState.activeTemplateId = "automation-testing-api";

    render(
      <PipelineRunPage
        templateId="automation-testing-api"
        hideLlmProfile
        showResultsInline
      />,
    );

    const button = screen.getByRole("button", { name: "New run" });
    // Must NOT be a dead button — the user has to be able to start over.
    expect(button).toBeEnabled();

    fireEvent.click(button);
    expect(storeState.clearSession).toHaveBeenCalledTimes(1);
    // No run is started without a document.
    expect(startMutation.mutateAsync).not.toHaveBeenCalled();
  });
});
