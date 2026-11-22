import { readFileSync } from 'node:fs';

export function visualButtonsDatasetPage() {
  const data = JSON.parse(readFileSync(new URL('../../../../benchmark/vision/visual-buttons/mongchiton-desktop.json', import.meta.url), 'utf8'));
  const escape = (value: string) => value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;');
  // Captured presentation, synthetic labels/assets/network destinations. The
  // expected annotation is deliberately not rendered into the page.
  const body = data.examples.map((e: { id: string; tag: string; features: { self: Record<string, string | number | boolean>; parent: Record<string, string | number | boolean> } }) => {
    const f = e.features.self, p = e.features.parent;
    const css = (v: typeof f) => `display:block;box-sizing:border-box;width:${f.width}px;height:${f.height}px;cursor:${v.cursor};border:${v.border} solid brown;border-radius:${v.radius};background-color:${v.color};background-image:${v.background === 'none' ? 'none' : 'linear-gradient(brown,gold)'};`;
    return `<section style="display:inline-block;vertical-align:top;margin:8px"><div style="${css(p)}position:relative">
      ${p.sprite_sibling ? '<svg style="position:absolute;pointer-events:none" width="20" height="20"></svg>' : ''}
      <${e.tag} data-example="${e.id}" ${e.tag === 'a' ? 'href="/fixture-destination"' : ''}
        ${f.onclick ? 'onclick="void 0"' : ''} style="${css(f)}${f.position === 'absolute' ? 'position:absolute;inset:0;' : ''}">${escape(String(f.label))}</${e.tag}>
    </div></section>`;
  }).join('');
  return `<!doctype html><html><body style="margin:0">${body}<script>
  document.addEventListener('click', event => {
    const target = event.target.closest('[data-example]');
    if (target) { event.preventDefault(); fetch('/record-button/' + target.dataset.example, {method:'POST'}); }
  });</script></body></html>`;
}
