import { test, expect } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { visualButtonSemantics } from './vision-button-semantics.js';
import { inspectState, setInteractionScope } from './vision-checkpoints.js';
import { observeDom, resolveDomTarget } from './vision-dom.js';
import { validateVision, type VisualWorkerObserveDom } from './vision-contract.js';
import { randomUUID } from 'node:crypto';

type Feature = { tag: string; label: string; background: string; color: string; border: string; radius: string; cursor: string; width: number; height: number; position: string; onclick: boolean; sprite_sibling?: boolean };
type Example = { id: string; expected: boolean; group: string; tag: string; label: string; features: { self: Feature; parent: Feature } };
const datasetPath = '../../benchmark/vision/visual-buttons/mongchiton-desktop.json';
const dataset = JSON.parse(readFileSync(datasetPath, 'utf8')) as { examples: Example[] };
const escape = (value: string) => value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;');
function style(f: Feature) {
  return `display:block;width:${f.width}px;height:${f.height}px;box-sizing:border-box;cursor:${f.cursor};border:${f.border} solid brown;border-radius:${f.radius};background-color:${f.color};background-image:${f.background === 'none' ? 'none' : 'linear-gradient(brown,gold)'};`;
}
function fixture(examples: Example[]) {
  return `<style>body{margin:8px}.example{margin:8px;position:relative;display:inline-block;vertical-align:top}</style>` + examples.map(e => {
    const f=e.features.self, p=e.features.parent;
    return `<section class="example"><div style="${style({...p,width:f.width,height:f.height})}position:relative">
      ${p.sprite_sibling ? '<svg style="position:absolute;inset:0;pointer-events:none" width="20" height="20"></svg>' : ''}
      <${e.tag} data-example="${e.id}" ${e.tag === 'a' ? 'href="#target"' : ''} style="${style(f)}${f.position === 'absolute' ? 'position:absolute;inset:0;' : ''}">${escape(f.label)}</${e.tag}>
      </div></section>`;
  }).join('');
}

test('manually annotated desktop dataset: 47 positives and 14 ordinary links', async ({ page }) => {
  await page.setContent(fixture(dataset.examples));
  await page.locator('[data-example]').evaluateAll((nodes, examples) => {
    for (const node of nodes) if (examples.find(e => e.id === node.getAttribute('data-example'))?.features.self.onclick) (node as HTMLElement).onclick = () => {};
  }, dataset.examples);
  const found=await page.evaluate(visualButtonSemantics);
  const ids=await page.evaluate(paths => paths.map(p => document.querySelector(p)?.getAttribute('data-example')), found.map(item=>item.path));
  const expected=dataset.examples.filter(e=>e.expected).map(e=>e.id);
  const falseNegatives=expected.filter(id=>!ids.includes(id));
  const falsePositives=ids.filter(id=>!expected.includes(id!));
  writeFileSync('../../benchmark/vision/visual-buttons/offline-result.json', JSON.stringify({schema_version:'visual-button-evaluation-v1',fixture:'mongchiton-desktop.json',positive_targets:47,negative_targets:14,true_positives:47-falseNegatives.length,false_negatives:falseNegatives,false_positives:falsePositives,scope:'synthetic reproduction of captured computed styles; no live execution claim'},null,2)+'\n');
  expect(falseNegatives).toEqual([]);
  expect(falsePositives).toEqual([]);
});

test('held-out affordances reject ordinary links and nested pointer decorations', async ({ page }) => {
  await page.setContent(`<button id="native"><span style="cursor:pointer">Save</span></button>
    <a id="styled" href="#" style="display:inline-block;padding:10px;border-radius:6px;background:blue">Open</a>
    <div id="custom" style="width:50px;height:50px;background:linear-gradient(red,blue);cursor:pointer"><span style="cursor:pointer">+</span></div>
    <a id="plain" href="#" style="cursor:pointer">Article</a>
    <a id="row" href="#" style="display:block;width:200px;border-bottom:1px solid;background:yellow">News title</a>
    <div style="opacity:0"><button id="hidden">Hidden</button></div>
    <div id="decoration" style="width:50px;height:50px;background:blue;cursor:pointer">Art</div>`);
  await page.locator('#custom').evaluate(el=>(el as HTMLElement).onclick=()=>{});
  const items=await page.evaluate(visualButtonSemantics);
  expect(await page.evaluate(paths=>paths.map(p=>document.querySelector(p)?.id),items.map(i=>i.path))).toEqual(['native','styled','custom']);
});

test('visual DOM keeps duplicate positions, true roles, and live-node replacement checks', async ({ page }) => {
  await page.setContent(`<style>a{display:inline-block;width:100px;height:40px;border-radius:6px;background:gold}</style>
    <a href="#" aria-label="Download">Download</a><a href="#" aria-label="Download">Download</a>
    <div style="width:60px;height:60px;cursor:pointer;background:linear-gradient(red,blue)"></div><p><a style="all:revert" href="#">Article</a></p>`);
  await page.locator('div').evaluate(el=>(el as HTMLElement).onclick=()=>{});
  setInteractionScope(page,'visual_buttons');
  const state=await inspectState(page);
  const request=validateVision<VisualWorkerObserveDom>('VisualWorkerObserveDom',{tenant_id:'fixture',project_id:randomUUID(),session_id:randomUUID(),fencing_token:1,expected_state_fingerprint:state.fingerprint,snapshot_id:randomUUID()});
  const snapshot=await observeDom(page,request);
  expect(snapshot.data.observation.skipped_count).toBe(0);
  expect(snapshot.data.observation.elements.map(e=>[e.role,e.button_kind])).toEqual([['link','styled_link'],['link','styled_link'],['generic','custom']]);
  expect(new Set(snapshot.data.bindings.map(b=>b.descriptor.value)).size).toBe(3);
  expect(snapshot.data.bindings.every(b=>b.descriptor.schema_version==='v3')).toBe(true);
  const first=snapshot.data.observation.elements[0];
  await resolveDomTarget(snapshot,page,first.element_id);
  await page.locator('a').first().evaluate(el=>el.replaceWith(el.cloneNode(true)));
  await expect(resolveDomTarget(snapshot,page,first.element_id)).rejects.toThrow();
});
