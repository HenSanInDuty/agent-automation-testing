import { test, expect, type Page } from "@playwright/test";

const dashboard = process.env.VISION_DASHBOARD_URL;
test.skip(!dashboard, "Set VISION_DASHBOARD_URL to the dashboard fixture server.");

async function fixture(page: Page, role = "tenant_admin") {
  let policy = { provider: "codex_cli", model: "gpt-6-luna", text_transfer_accepted: true, max_seconds: 120 };
  const writes: typeof policy[] = [];
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/test-generations/provider")) {
      if (route.request().method() === "PUT") { policy = route.request().postDataJSON(); writes.push(policy); }
      return route.fulfill({ json: { policy, revision: "fixture", providers: [
        { id: "codex_cli", label: "Codex", model: "gpt-6-luna", configured: true },
        { id: "huggingface", label: "Hugging Face", model: "fixture/hf", configured: true },
      ] } });
    }
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { role, tenant_id: "fixture", email: "fixture@example.test" } });
    if (path.endsWith("/projects")) return route.fulfill({ json: [] });
    if (path.endsWith("/vision/policy")) return route.fulfill({ json: { enabled: false, provider: "huggingface", model: "fixture/hf" } });
    return route.fulfill({ json: { items: [], total: 0 } });
  });
  return writes;
}

test("generation provider switches explicitly and survives refresh", async ({ page }) => {
  const writes = await fixture(page);
  await page.goto(`${dashboard}/agent`);
  const settings = page.getByRole("region", { name: "Test generation provider", exact: true });
  await expect(settings.getByRole("button", { name: "Codex", exact: true })).toHaveAttribute("aria-pressed", "true");
  await settings.getByRole("button", { name: "Hugging Face", exact: true }).click();
  const consent = settings.getByRole("checkbox");
  await expect(consent).not.toBeChecked();
  await expect(settings.getByText("Unsaved changes.", { exact: false })).toBeVisible();
  expect(writes).toHaveLength(0);
  await consent.check();
  await settings.getByRole("button", { name: "Save generation provider" }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toMatchObject({ provider: "huggingface", model: "fixture/hf", text_transfer_accepted: true });
  await page.reload();
  await expect(settings.getByRole("button", { name: "Hugging Face", exact: true })).toHaveAttribute("aria-pressed", "true");
  await settings.getByRole("button", { name: "Codex", exact: true }).click();
  await expect(consent).not.toBeChecked();
  await consent.check();
  await settings.getByRole("button", { name: "Save generation provider" }).click();
  await expect.poll(() => writes.length).toBe(2);
  expect(writes[1].provider).toBe("codex_cli");
});

test("viewers can inspect the saved provider but cannot switch", async ({ page }) => {
  const writes = await fixture(page, "viewer");
  await page.goto(`${dashboard}/agent`);
  const settings = page.getByRole("region", { name: "Test generation provider", exact: true });
  await expect(settings.getByRole("button", { name: "Hugging Face", exact: true })).toBeDisabled();
  await expect(settings.getByRole("button", { name: "Save generation provider" })).toHaveCount(0);
  expect(writes).toHaveLength(0);
});
