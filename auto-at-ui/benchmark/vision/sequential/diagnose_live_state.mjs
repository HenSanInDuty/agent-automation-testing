// Read-only state drift probe, run in the deployed worker image without app mounts.
import { chromium } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { inspectState, equivalentState } from './src/vision-checkpoints.ts';

const digest = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 720 },
  acceptDownloads: false, serviceWorkers: 'block', reducedMotion: 'reduce' });
const evaluate = page.evaluate.bind(page);
let interactions = [], semantics = [];
page.evaluate = async (...args) => {
  const result = await evaluate(...args);
  if (result && Array.isArray(result.interactions)) {
    interactions = result.interactions;
    semantics = result.semantics;
  }
  return result;
};
const report = { target: 'https://mongchiton.vn/', model_calls: 0, clicks: 0,
  reduced_motion: 'reduce', service_workers: 'block',
  diagnostic_intervention: process.argv.includes('--pause-character-autoplay')
    ? 'Stop only the character carousel autoplay in this disposable browser' : null,
  worker_source_sha256: createHash('sha256').update(readFileSync('./src/vision-checkpoints.ts')).digest('hex'),
  samples: [] };
function fieldDiff(a, b) {
  return { interaction: a.interaction_fingerprint !== b.interaction_fingerprint,
    semantics: a.semantic_fingerprint !== b.semantic_fingerprint,
    url: a.url_fingerprint !== b.url_fingerprint,
    form_presence: a.form_presence_fingerprint !== b.form_presence_fingerprint,
    form_values: a.privateForms !== b.privateForms,
    scroll: a.scroll_x !== b.scroll_x || a.scroll_y !== b.scroll_y };
}
function safe(row) {
  if (!Array.isArray(row?.[2])) return { tag: row?.[1], landmark: true };
  const attrs = Object.fromEntries(row[2]);
  const semantic = semantics.find(item => item[1] === row[1] &&
    JSON.stringify(item[5]) === JSON.stringify(row[6]));
  return { tag: row[1], id: attrs.id, role: attrs.role,
    classes_at_current_sample: semantic ? Object.fromEntries(semantic[2]).class ?? null : null,
    bounds: row[6], hit_test: row[11], label_hash: digest(row[5]),
    identity_hash: digest(row[2]) };
}
function changes(before, after) {
  const changes = [];
  for (let i = 0; i < Math.max(before.length, after.length); i++) {
    const a = before[i], b = after[i];
    if (JSON.stringify(a) === JSON.stringify(b)) continue;
    const fields = [];
    for (let j = 0; j < Math.max(a?.length ?? 0, b?.length ?? 0); j++) {
      if (JSON.stringify(a?.[j]) !== JSON.stringify(b?.[j])) fields.push(j);
    }
    changes.push({ index: i, fields, before: safe(a), after: safe(b) });
  }
  return changes;
}
try {
  await page.goto(report.target, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(3000);
  for (const scrollY of process.argv.includes('--focus') ? [1136] : [0, 560, 1136]) {
    await page.evaluate(y => window.scrollTo(0, y), scrollY);
    if (process.argv.includes('--pause-character-autoplay')) {
      report.intervention_applied = await page.evaluate(() => {
        const swiper = document.querySelector('.character-mount-swiper')?.swiper;
        if (!swiper?.autoplay) return false;
        swiper.autoplay.stop(); return true;
      });
    }
    await page.waitForTimeout(1000);
    let prior = await inspectState(page), priorInteractions = interactions;
    const initialFingerprint = prior.fingerprint;
    const began = Date.now();
    for (let sample = 1; sample <= 12; sample++) {
      await page.waitForTimeout(1000);
      const next = await inspectState(page);
      report.samples.push({ requested_scroll_y: scrollY, actual_scroll_y: next.scroll_y,
        elapsed_ms: Date.now() - began, sample, fingerprint: next.fingerprint,
        equivalent_to_previous: equivalentState(prior, next),
        fingerprint_matches_initial: next.fingerprint === initialFingerprint,
        components_changed: fieldDiff(prior, next),
        interaction_count_before: priorInteractions.length,
        interaction_count_after: interactions.length,
        changed_interactions: changes(priorInteractions, interactions),
      });
      report.samples.at(-1).carousel = await page.evaluate(() => {
        const swiper = document.querySelector('.character-mount-swiper')?.swiper;
        return swiper ? { real_index: swiper.realIndex, active_index: swiper.activeIndex,
          autoplay_running: swiper.autoplay?.running, autoplay_paused: swiper.autoplay?.paused,
          delay_ms: swiper.params.autoplay?.delay, transition_ms: swiper.params.speed,
        } : null;
      });
      prior = next; priorInteractions = interactions;
    }
    report.samples.at(-1).visible_control_styles = await page.evaluate(() =>
      Array.from(document.querySelectorAll('*')).flatMap(el => {
        const r = el.getBoundingClientRect(), s = getComputedStyle(el);
        if (r.bottom <= 0 || r.top >= innerHeight || r.right <= 0 || r.left >= innerWidth ||
            r.width <= 0 || r.height <= 0 || s.visibility !== 'visible' ||
            !(el.matches('button,a[href],[role="button"],[onclick]') || s.cursor === 'pointer')) return [];
        const motion = [];
        for (let node = el; node && node !== document.body; node = node.parentElement) {
          const style = getComputedStyle(node);
          if (style.animationName !== 'none' || node.getAnimations().length) {
            motion.push({ tag: node.tagName, classes: String(node.className).slice(0, 200),
              css_animation: style.animationName, transform: style.transform,
              animations: node.getAnimations().map(a => ({ kind: a.constructor.name,
                name: a.animationName ?? null, state: a.playState,
                duration: a.effect?.getTiming().duration, iterations: a.effect?.getTiming().iterations,
              })) });
          }
        }
        return [{ tag: el.tagName, id: el.id, classes: String(el.className).slice(0, 160),
          animation: s.animationName, transition: s.transitionProperty,
          bounds: [r.left, r.top, r.right, r.bottom].map(Math.round), motion }];
      }));
  }
  console.log(JSON.stringify(report));
} finally { await browser.close(); }
