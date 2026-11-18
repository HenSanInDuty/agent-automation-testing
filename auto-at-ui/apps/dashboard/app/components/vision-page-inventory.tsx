import type { VisualPageInventory } from "../generation-types";

export function VisionPageInventoryList({ pages, live, onSelect }: {
  pages: VisualPageInventory[]; live: boolean; onSelect: (id: string) => void;
}) {
  if (!pages.length) return null;
  return <section className="workspace-section" aria-label="Page interaction inventory">
    <h2>Pages and interactions</h2>
    <p>Saved URLs and controls found in each observed page state. Counts cover visible, safely identifiable controls; scrolling or opening menus can reveal more.</p>
    {pages.map((page, index) => {
      const completed = page.controls.filter((control) => control.status === "completed").length;
      const remaining = page.controls.filter((control) => ["pending", "queued"].includes(control.status)).length;
      return <details key={page.state_id} open={index === 0} className="vision-page-inventory">
        <summary>{page.page_url ?? "Page URL unavailable"} — {page.controls.length} controls · {completed} performed · {remaining} remaining</summary>
        {page.interaction_scope === "visual_buttons" && <p>Scope: visual buttons, including button-shaped links and custom controls. Ordinary content links are excluded.</p>}
        {page.interaction_scope === "buttons" && <p>Scope: buttons only. Links and other control types are excluded.</p>}
        {page.page_url && <p><a href={page.page_url} target="_blank" rel="noopener noreferrer">Open saved URL</a> <small>Query parameters and fragments are omitted.</small></p>}
        {(page.truncated || page.scrollable || page.skipped_count > 0) && <p>Partial page inventory{page.scrollable ? ": more content can be reached by scrolling" : ""}. {page.skipped_count} controls or elements could not be safely inventoried.</p>}
        {!live && remaining > 0 && <p>{remaining} controls remain untested in this recorded state. Finishing a session does not mean every control was tested.</p>}
        <ul className="stack-list">{page.controls.map((control, controlIndex) => <li key={control.key}>
          <strong>{control.name || `Unnamed ${control.role} ${controlIndex + 1}`}</strong> <span>({control.role}) · {control.status === "queued" && !live ? "not attempted" : control.status}</span>
          {control.operation_id && <button type="button" className="button button--secondary" onClick={() => onSelect(control.operation_id!)}>Show recorded action</button>}
        </li>)}</ul>
      </details>;
    })}
  </section>;
}
