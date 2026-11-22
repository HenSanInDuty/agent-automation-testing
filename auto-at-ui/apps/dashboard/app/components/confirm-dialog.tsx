"use client";

import { useRef } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Spinner } from "@/components/ui/spinner";
import { dialogKeyboardAction, initialDialogFocus } from "./confirm-dialog-model";

export function ConfirmDialog({ open, title, description, confirmLabel, onConfirm, onCancel, busy = false, tone = "destructive" }: {
  open: boolean; title: string; description: string; confirmLabel: string; onConfirm: () => void; onCancel: () => void; busy?: boolean; tone?: "destructive" | "default";
}) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  return <Dialog open={open} onOpenChange={(next) => { if (!next && !busy) onCancel(); }}>
    <DialogContent
      showCloseButton={false}
      className="sm:max-w-md"
      onOpenAutoFocus={(event) => { event.preventDefault(); cancelRef.current?.focus(); }}
      onEscapeKeyDown={(event) => { if (dialogKeyboardAction(event.key, busy) !== "cancel") event.preventDefault(); }}
      onInteractOutside={(event) => event.preventDefault()}
    >
      <DialogHeader>
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>
      </DialogHeader>
      <DialogFooter>
        <Button ref={cancelRef} data-initial-focus={initialDialogFocus} type="button" variant="outline" onClick={onCancel} disabled={busy}>Cancel</Button>
        <Button type="button" variant={tone} onClick={onConfirm} disabled={busy}>{busy && <Spinner />}{busy ? "Working…" : confirmLabel}</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>;
}
