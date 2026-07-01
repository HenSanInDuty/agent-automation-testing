import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { pipelineApi } from "../../../api/client";
import { DocumentTemplateConverter } from "../DocumentTemplateConverter";

describe("DocumentTemplateConverter", () => {
  afterEach(() => vi.restoreAllMocks());

  it("converts, previews, and applies a pipeline Markdown file", async () => {
    vi.spyOn(pipelineApi, "convertDocument").mockResolvedValue({
      filename: "requirements-pipeline.md",
      markdown: "# Converted API\n\n- Base URL: https://api.example.test",
      validation: {
        valid: true,
        code: "",
        detail: "",
        missing_sections: [],
        missing_fields: [],
        field_errors: [],
        warnings: [],
      },
    });
    const onApply = vi.fn();

    render(
      <DocumentTemplateConverter
        sourceFile={new File(["source"], "requirements.docx")}
        onApply={onApply}
      />,
    );

    fireEvent.change(screen.getByLabelText("API base URL"), {
      target: { value: "https://api.example.test" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Convert document" }));

    expect(await screen.findByText("Generated requirements-pipeline.md")).toBeInTheDocument();
    expect(screen.getByLabelText("Converted pipeline document")).toHaveValue(
      "# Converted API\n\n- Base URL: https://api.example.test",
    );

    fireEvent.click(screen.getByRole("button", { name: "Use converted document" }));
    await waitFor(() => expect(onApply).toHaveBeenCalledOnce());
    expect(onApply.mock.calls[0][0]).toMatchObject({
      name: "requirements-pipeline.md",
      type: "text/markdown;charset=utf-8",
    });
  });
});
