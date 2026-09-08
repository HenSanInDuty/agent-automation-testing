import type { VisualLocator } from "../generation-types";

export function VisionLocatorCatalog({ items, hasMore, onMore }: { items: VisualLocator[]; hasMore: boolean; onMore: () => void }) {
  return <section className="workspace-section" aria-label="Locator catalog"><h2>Recorded locators</h2>
    <p>Verification describes the element at exploration time. Future page changes can still make a test fail.</p>
    {items.length ? <ul className="stack-list">{items.map((item) => <li key={item.id}><strong>{item.status === "verified" ? "Verified locator" : "Unresolved locator"}</strong> {item.descriptor ? <code>{item.descriptor.strategy}{item.descriptor.role ? ` ${item.descriptor.role}` : ""}: {item.descriptor.value}</code> : item.reason_code?.replaceAll("_", " ")}{item.descriptor?.scope.map((scope, index) => <small key={index}> · {scope.kind}: {scope.selector}</small>)}</li>)}</ul> : <p>No locator evidence is available.</p>}
    {hasMore && <button type="button" className="button button--secondary" onClick={onMore}>More locators</button>}
  </section>;
}
