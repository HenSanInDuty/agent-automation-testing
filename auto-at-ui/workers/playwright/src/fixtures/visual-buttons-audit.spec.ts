import { test, expect } from '@playwright/test';
import { matchAnnotations, type AuditedElement, type Annotation } from './visual-buttons-audit-model.js';

const element = (path: string): AuditedElement => ({ path, classes: 'button', label: 'Download', tag: 'a',
  href: 'https://example.invalid/download', target: '_blank', box: { x: 0, y: 0, width: 40, height: 40 } });
const annotation = (id: string): Annotation => ({ id, expected: true, tag: 'a', label: 'Download',
  reference_class: 'button', group: 'fixture' });

test('duplicates at separate positions remain distinct; repeated snapshots do not', () => {
  const result = matchAnnotations([annotation('one'), annotation('two')], [element('a'), element('a'), element('b')]);
  expect(result.matches.map(m => [m.expected_id, m.path])).toEqual([['one', 'a'], ['two', 'b']]);
  expect(result.missing).toEqual([]);
});
test('reviewed structural location cannot be replaced by the same text elsewhere', () => {
  const result = matchAnnotations([{ ...annotation('one'), reference_path: 'a' }], [element('b')]);
  expect(result.missing).toEqual(['one']);
  expect(result.unmatched.map(e => e.path)).toEqual(['b']);
});
test('negative labels remain visible in classifier false positives', () => {
  const result = matchAnnotations([{ ...annotation('plain'), expected: false }], [element('a')]);
  expect(result.matches[0].expected).toBe(false);
});
