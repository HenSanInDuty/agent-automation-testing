import type { ReactNode } from "react";
import { stateAccessibility } from "./state-model";

type StateProps = { title: string; children?: ReactNode; action?: ReactNode };

export function EmptyState({ title, children, action }: StateProps) {
  const accessibility = stateAccessibility("empty");
  return <section className="state-card" aria-label={accessibility.ariaLabel}><div className="state-card__icon" aria-hidden="true">—</div><h2>{title}</h2>{children && <p>{children}</p>}{action}</section>;
}

export function LoadingState({ title = "Loading" }: { title?: string }) {
  const accessibility = stateAccessibility("loading");
  return <section className="state-card" aria-busy={accessibility.busy} aria-label={accessibility.ariaLabel}><span className="loading-mark" aria-hidden="true" /><h2>{title}</h2><p>Please wait while the control plane responds.</p></section>;
}

export function ErrorState({ title = "Something went wrong", children, action }: StateProps) {
  const accessibility = stateAccessibility("error");
  return <section className="state-card state-card--error" role={accessibility.role} aria-label={accessibility.ariaLabel}><div className="state-card__icon" aria-hidden="true">!</div><h2>{title}</h2>{children && <p>{children}</p>}{action}</section>;
}
