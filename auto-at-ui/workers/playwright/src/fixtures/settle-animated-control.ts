// Synthetic homepage fragments for the settle tolerance (r13 diagnosis, r14 fix, ADR 042). The pulse is a
// pure-presentation, infinite CSS animation on the ancestor of a full-cover link (same shape as the live
// "play now" widget). Nothing about the control's identity, label, href, state or form data changes.
const head = (keyframes: string, rule: string) => `<!doctype html><meta charset="utf-8"><style>
  body{margin:0;font:14px sans-serif}
  ${keyframes}
  .widget{position:absolute;left:600px;top:300px;width:94px;height:72px;${rule}}
  .widget a{position:absolute;inset:0;display:block;cursor:pointer}
</style>
<button type="button">Static control</button>`;
const widget = `<div class="widget"><a href="#play" aria-label="Play now"></a></div>`;
const pulse = (scale: number, animated = true) => head(
  `@keyframes play-now-pulse{0%,100%{transform:scale(1)}50%{transform:scale(${scale})}}`,
  animated ? "animation:play-now-pulse 1.2s ease-in-out infinite;" : "") + widget;

export const pulsingControlHtml = pulse(1.06);
export const staticControlHtml = pulse(1.06, false);
// Amplitude far beyond the IoU tolerance: only the layout box (B) keeps this equal.
export const strongPulseHtml = pulse(1.5);
// Rotation + opacity only: also eligible.
export const spinFadeHtml = head(
  "@keyframes spin{0%{transform:rotate(0);opacity:1}50%{transform:rotate(40deg);opacity:.4}100%{transform:rotate(0);opacity:1}}",
  "animation:spin 1.2s linear infinite;") + widget;
// Infinite animations that really move or resize the control: never eligible, tolerance alone must catch them.
export const marqueeTranslateHtml = head("@keyframes slide{0%{transform:translateX(0)}100%{transform:translateX(-300px)}}",
  "animation:slide 1.2s linear infinite;") + widget;
export const leftAnimationHtml = head("@keyframes drift{0%{left:600px}100%{left:900px}}", "animation:drift 1.2s linear infinite;") + widget;
export const widthAnimationHtml = head("@keyframes grow{0%{width:94px}100%{width:200px}}", "animation:grow 1.2s linear infinite;") + widget;
// Script-driven carousel (swiper-like): the wrapper translate is a plain style, not an animation. A pulse sits next
// to it so the page has an eligible animation too.
export const carouselHtml = pulse(1.5) + `<div id="viewport" style="position:absolute;left:100px;top:100px;width:300px;height:80px;overflow:hidden">
  <div id="track" style="display:flex;width:900px;transform:translateX(0)">
    <div style="width:300px"><a href="#s1">Slide 1</a></div><div style="width:300px"><a href="#s2">Slide 2</a></div>
    <div style="width:300px"><a href="#s3">Slide 3</a></div></div></div>`;
