import { readFileSync } from "node:fs";
import { test, expect } from "@playwright/test";

// Explicit local smoke fixture only; never use a real user's password.
const fixturePath = process.env.DASHBOARD_AUTH_FIXTURE;
const urls = (process.env.DASHBOARD_AUTH_URLS ?? "").split(",").filter(Boolean);
const account = fixturePath ? JSON.parse(readFileSync(fixturePath, "utf8")) as {
  tenant: string; email: string; password: string;
} : null;
test.use({ launchOptions: { args: ["--host-resolver-rules=MAP localhost 127.0.0.1"] } });

for (const base of urls.length ? urls : ["http://127.0.0.1:3000"]) {
  test(`login keeps cookies and CSRF on dashboard origin: ${base}`, async ({ page }) => {
    test.skip(!account || !urls.length, "Requires an explicitly provisioned disposable local account.");
    const apiOrigins = new Set<string>();
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.pathname.startsWith("/api/")) apiOrigins.add(url.origin);
    });
    await page.goto(`${base}/login`);
    await page.getByLabel("Tenant", { exact: true }).fill(account!.tenant);
    await page.getByLabel("Email", { exact: true }).fill(account!.email);
    await page.getByLabel("Password", { exact: true }).fill(account!.password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page).toHaveURL(`${base}/`);
    await expect(page.getByLabel("Current user menu")).toContainText(account!.email);
    const cookies = await page.context().cookies(base);
    const session = cookies.find((cookie) => cookie.name === "auto_at_session");
    expect(session?.httpOnly).toBe(true);
    expect(session?.sameSite).toBe("Lax");
    expect(cookies.some((cookie) => cookie.name === "auto_at_csrf" && !cookie.httpOnly)).toBe(true);
    await page.reload();
    await expect(page.getByLabel("Current user menu")).toContainText(account!.email);
    expect(await page.evaluate(async () => (await fetch("/api/v1/auth/me")).status)).toBe(200);
    expect(await page.evaluate(async () => (await fetch("/api/v1/auth/logout", { method: "POST" })).status)).toBe(403);
    await page.getByLabel("Current user menu").click();
    const logout = page.waitForResponse((response) => response.url().endsWith("/api/v1/auth/logout") && response.status() === 204);
    await page.getByRole("button", { name: "Sign out" }).click();
    await logout;
    await expect(page).toHaveURL(`${base}/login`);
    expect(await page.evaluate(async () => (await fetch("/api/v1/auth/me")).status)).toBe(401);
    expect([...apiOrigins]).toEqual([new URL(base).origin]);
  });
}

test("login recovers after a network failure", async ({ page }) => {
  test.skip(!urls.length, "Requires an explicit local dashboard URL.");
  await page.goto(`${urls[0]}/login`);
  await page.route("**/api/v1/auth/login", (route) => route.abort());
  await page.getByLabel("Email", { exact: true }).fill("unreachable@example.test");
  await page.getByLabel("Password", { exact: true }).fill("Synthetic-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.locator("form").getByRole("alert")).toHaveText("Cannot reach the server. Please try again.");
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeEnabled();
});
