import type { RequestState } from "./generation-types";

/** The browser only polls states owned by asynchronous control-plane work. */
export function shouldPollGeneration(state: RequestState): boolean {
  return state === "queued" || state === "generating";
}
