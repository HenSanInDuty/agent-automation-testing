"use client";

import { useEffect, useRef } from "react";
import { dialogKeyboardAction, initialDialogFocus } from "./confirm-dialog-model";

export function ConfirmDialog({ open, title, description, confirmLabel, onConfirm, onCancel, busy = false }: {
  open: boolean; title: string; description: string; confirmLabel: string; onConfirm: () => void; onCancel: () => void; busy?: boolean;
}) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  useEffect(() => { if (open) cancelRef.current?.focus(); }, [open]);
  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (dialogKeyboardAction(event.key, busy) === "cancel") onCancel(); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [busy, onCancel, open]);
  if (!open) return null;
  return <div className="dialog-backdrop" role="presentation"><section className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-dialog-title" aria-describedby="confirm-dialog-description"><h2 id="confirm-dialog-title">{title}</h2><p id="confirm-dialog-description">{description}</p><div className="dialog-actions"><button ref={cancelRef} data-initial-focus={initialDialogFocus} type="button" className="button button--secondary" onClick={onCancel} disabled={busy}>Cancel</button><button type="button" className="button button--danger" onClick={onConfirm} disabled={busy}>{busy ? "Working…" : confirmLabel}</button></div></section></div>;
}
