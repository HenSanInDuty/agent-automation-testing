import type { VisualReplayFrame } from "../generation-types";

export function orderedReplayFrames(frames: VisualReplayFrame[]): VisualReplayFrame[] {
  return [...frames].sort((left, right) => left.sequence - right.sequence || left.id.localeCompare(right.id));
}

export function replayMarkerPosition(
  action: { x?: number; y?: number }, image: { width: number; height: number },
): { left: string; top: string } | null {
  if (
    !Number.isFinite(action.x) || !Number.isFinite(action.y) || image.width <= 0 || image.height <= 0
  ) return null;
  const left = Math.min(100, Math.max(0, (action.x! / image.width) * 100));
  const top = Math.min(100, Math.max(0, (action.y! / image.height) * 100));
  return { left: `${left}%`, top: `${top}%` };
}
