import type { CDPSession, Page } from "@playwright/test";
import { VisionWorkerError } from "./vision-contract.js";

// Read the rendered viewport without waiting for web fonts or altering the page.
export async function captureVisionScreen(page: Page, timeout: number): Promise<Buffer> {
  let client: CDPSession | undefined;
  let expired = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const capture = async () => {
    client = await page.context().newCDPSession(page);
    if (expired) { void client.detach().catch(() => undefined); throw new VisionWorkerError("capture_failed"); }
    const frame = await client.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    return Buffer.from(frame.data, "base64");
  };
  try {
    return await Promise.race([capture(), new Promise<never>((_, reject) => {
      timer = setTimeout(() => { expired = true; reject(new VisionWorkerError("capture_failed")); }, timeout);
    })]);
  } finally {
    if (timer) clearTimeout(timer);
    void client?.detach().catch(() => undefined);
  }
}
