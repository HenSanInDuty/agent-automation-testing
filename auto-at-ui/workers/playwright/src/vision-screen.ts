import type { CDPSession, Page } from "@playwright/test";
import { VisionWorkerError } from "./vision-contract.js";
import { logVisionFailure, visionErrorType } from "./vision-observability.js";

// Read the rendered viewport without waiting for web fonts or altering the page.
export async function captureVisionScreen(page: Page, timeout: number, fastLossless = false): Promise<Buffer> {
  let client: CDPSession | undefined;
  let expired = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const started = performance.now();
  let captureStage = "cdp_session";
  const capture = async () => {
    client = await page.context().newCDPSession(page);
    if (expired) { void client.detach().catch(() => undefined); throw new VisionWorkerError("capture_failed"); }
    captureStage = "screenshot";
    const frame = await client.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false,
      ...(fastLossless ? { optimizeForSpeed: true } : {}) });
    return Buffer.from(frame.data, "base64");
  };
  try {
    return await Promise.race([capture(), new Promise<never>((_, reject) => {
      timer = setTimeout(() => { expired = true; reject(new VisionWorkerError("capture_failed")); }, timeout);
    })]);
  } catch (error) {
    logVisionFailure("vision.capture.failed", {
      capture_stage: captureStage, error_type: expired ? "timeout" : visionErrorType(error),
      timeout_ms: Math.round(timeout), duration_ms: Math.round(performance.now() - started),
      page_closed: page.isClosed(), browser_connected: page.context().browser()?.isConnected() ?? false,
    });
    throw error;
  } finally {
    if (timer) clearTimeout(timer);
    void client?.detach().catch(() => undefined);
  }
}
