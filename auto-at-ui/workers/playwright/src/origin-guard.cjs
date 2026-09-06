/* Loaded into every Playwright Test worker before untrusted test modules. */
const fs = require("node:fs");

const allowed = new Set(JSON.parse(process.env.PLAYWRIGHT_ALLOWED_ORIGINS || "[]"));
const allowAllOrigins = allowed.has("*");
const evidencePath = process.env.PLAYWRIGHT_POLICY_EVIDENCE;
const attempted = new Set();

function record(url) {
  try {
    const parsed = new URL(url);
    if (!["http:", "https:"].includes(parsed.protocol)) {
      attempted.add("invalid-url");
    } else if (allowAllOrigins || allowed.has(parsed.origin)) {
      return true;
    } else {
      // Evidence deliberately records only the origin: query strings may contain PII.
      attempted.add(parsed.origin);
    }
  } catch {
    attempted.add("invalid-url");
  }
  if (evidencePath) fs.writeFileSync(evidencePath, JSON.stringify([...attempted]));
  return false;
}

function guardContext(context) {
  context.route("**/*", (route) => record(route.request().url()) ? route.continue() : route.abort());
  return context;
}

// @playwright/test and playwright-core share these BrowserType instances in a
// worker process.  Wrapping launch covers all fixture-created contexts before
// a page, popup, frame, redirect, or subresource can navigate.
for (const packageName of ["playwright-core", "playwright"]) {
  try {
    const playwright = require(packageName);
    for (const name of ["chromium", "firefox", "webkit"]) {
      const browserType = playwright[name];
      if (!browserType || browserType.__autoAtOriginGuard) continue;
      const launch = browserType.launch.bind(browserType);
      browserType.launch = async (...args) => {
        const browser = await launch(...args);
        const newContext = browser.newContext.bind(browser);
        browser.newContext = async (...contextArgs) => guardContext(await newContext(...contextArgs));
        return browser;
      };
      browserType.__autoAtOriginGuard = true;
    }
  } catch { /* The package is optional in the runner image. */ }
}

process.on("exit", () => {
  if (evidencePath && !fs.existsSync(evidencePath)) fs.writeFileSync(evidencePath, "[]");
});
