export function dialogKeyboardAction(key: string, busy: boolean): "cancel" | null {
  return key === "Escape" && !busy ? "cancel" : null;
}

export const initialDialogFocus = "cancel";
