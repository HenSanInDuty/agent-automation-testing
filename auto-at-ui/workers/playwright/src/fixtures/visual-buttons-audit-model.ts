/** Evaluation-only matching; never used by the production classifier. */
export type Annotation = { id: string; expected: boolean; tag: string; reference_class: string; label: string; group: string; reference_path?: string };
export type AuditedElement = {
  path: string; classes: string; label: string; tag: string; href: string | null; target: string | null;
  actionable?: boolean; href_sha256?: string | null;
  box: { x: number; y: number; width: number; height: number };
};
export function matchAnnotations(examples: Annotation[], entries: AuditedElement[]) {
  const pending = [...examples], matches: { expected_id: string; expected: boolean; path: string }[] = [];
  const unmatched: AuditedElement[] = [];
  for (const entry of [...new Map(entries.map(e => [e.path, e])).values()]) {
    const index = pending.findIndex(e => e.tag === entry.tag &&
      (e.reference_path ? e.reference_path === entry.path :
        entry.classes.trim().startsWith(e.reference_class.trim().slice(0, 55)) && (!e.label || e.label === entry.label)));
    if (index < 0) { unmatched.push(entry); continue; }
    const [annotation] = pending.splice(index, 1);
    matches.push({ expected_id: annotation.id, expected: annotation.expected, path: entry.path });
  }
  return { matches, missing: pending.map(e => e.id), unmatched };
}

