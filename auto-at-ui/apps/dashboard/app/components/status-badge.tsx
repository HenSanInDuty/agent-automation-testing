import type { ReactNode } from "react";
import { statusLabel, statusTone } from "./status-model";

export { statusLabel, statusTone } from "./status-model";

export function StatusBadge({ status, children }: { status: string; children?: ReactNode }) {
  return <span className={`status-badge status-badge--${statusTone(status)}`}>{children ?? statusLabel(status)}</span>;
}
