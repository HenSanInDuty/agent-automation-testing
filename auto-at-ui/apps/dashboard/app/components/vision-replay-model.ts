import type { VisualReplayFrame, VisualTrajectory, VisualTrajectoryEdge } from "../generation-types";

export function orderedReplayFrames(frames: VisualReplayFrame[]): VisualReplayFrame[] {
  return [...frames].sort((left, right) => left.sequence - right.sequence || left.id.localeCompare(right.id));
}

export function replayMarkerPosition(
  action: { x?: number; y?: number }, _image?: { width: number; height: number },
): { left: string; top: string } | null {
  void _image;
  if (
    !Number.isFinite(action.x) || !Number.isFinite(action.y)
  ) return null;
  // Vision actions use viewport-normalized coordinates (0..1), not pixels.
  const left = Math.min(100, Math.max(0, action.x! * 100));
  const top = Math.min(100, Math.max(0, action.y! * 100));
  return { left: `${left}%`, top: `${top}%` };
}

export function orderedAlternatives(trajectory: VisualTrajectory, stateId: string): VisualTrajectoryEdge[] {
  return trajectory.edges.filter((edge) => edge.parent_state_id === stateId).sort((a, b) => b.confidence - a.confidence || a.id.localeCompare(b.id));
}

export function defaultTrajectoryPath(trajectory: VisualTrajectory): VisualTrajectoryEdge[] {
  const states = new Map(trajectory.states.map((state) => [state.id, state]));
  const roots = trajectory.states.filter((state) => !state.parent_id).sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0) || a.id.localeCompare(b.id));
  let stateId = roots[0]?.id;
  const path: VisualTrajectoryEdge[] = [];
  const seen = new Set<string>();
  while (stateId && !seen.has(stateId)) {
    seen.add(stateId);
    const candidates = orderedAlternatives(trajectory, stateId).filter((edge) => Boolean(edge.child_state_id) && (edge.status === "observed" || edge.status === "no_meaningful_change"));
    if (!candidates.length) break;
    const edge = candidates[0]; path.push(edge); stateId = edge.child_state_id!;
    if (!states.has(stateId)) break;
  }
  return path;
}

export function boundedStep(index: number, length: number): number { return Math.max(0, Math.min(Math.max(0, length - 1), index)); }

export function trajectoryPathForEdge(trajectory: VisualTrajectory, edgeId: string): VisualTrajectoryEdge[] {
  const chosen = trajectory.edges.find((edge) => edge.id === edgeId);
  if (!chosen) return defaultTrajectoryPath(trajectory);
  const prefix: VisualTrajectoryEdge[] = [chosen];
  const seen = new Set([chosen.id]);
  let parent = trajectory.edges.find((edge) => edge.child_state_id === chosen.parent_state_id);
  while (parent && !seen.has(parent.id)) {
    prefix.unshift(parent); seen.add(parent.id);
    parent = trajectory.edges.find((edge) => edge.child_state_id === parent!.parent_state_id);
  }
  let child = chosen.child_state_id;
  const visitedStates = new Set(prefix.map((edge) => edge.parent_state_id));
  while (child && !visitedStates.has(child)) {
    visitedStates.add(child);
    const next = orderedAlternatives(trajectory, child).find((edge) => !seen.has(edge.id) && ["observed", "no_meaningful_change"].includes(edge.status));
    if (!next) break;
    seen.add(next.id); prefix.push(next); child = next.child_state_id;
  }
  return prefix;
}
