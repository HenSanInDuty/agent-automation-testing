# Visual-button regression dataset

This dataset corrects the semantic-HTML-only interpretation of “all buttons”.
Ground truth comes from manual inspection of the desktop screenshot and DOM on
https://mongchiton.vn/ on 2026-11-01, not from the production classifier output.

`mongchiton-desktop.json` contains 61 annotated UI positions: 47 positives
(15 native buttons, 28 styled links, four custom controls) and 14 negatives
(article titles, gallery images, the news thumbnail and footer text links).
`mongchiton-desktop.png` records the reviewed page. Floating duplicates count as
separate positions even when they have the same name or destination. Labels and
computed presentation are public website metadata; there are no credentials,
form values, private sessions, model responses or authentication cookies.

The scope is the initial desktop page and a full vertical scroll. It is **not**
an exhaustive annotation of hidden tabs, modals, mobile layouts or other pages.
Additional states require additional annotations; never hard-code 47 in runtime
completion logic. The production classifier contains no site domain, CSS class,
label list or expected count. This is evaluation data, not a model training run.

## Reproduction

From `workers/playwright/`:

```powershell
npx.cmd playwright test src/vision-visual-buttons.spec.ts --workers=1
npx.cmd tsx src/fixtures/visual-buttons-audit.ts
```

The first command tests synthetic reproductions of captured computed styles and
separate held-out cases (ordinary pointer links, a hover-like article row, nested
icons, transparent ancestors, duplicate labels and replaced DOM nodes). Asset
images are replaced with synthetic gradients; it does not contact the live site.
The second performs a read-only live scan, compares the independently annotated
targets, and verifies fresh worker bindings. It never clicks or invokes a model.
Inspect `offline-result.json` and `live-audit.json`, including missing and
unexpected target lists. A changed site requires review, not relabeling a miss
as an expected positive automatically.

With the isolated PostgreSQL fixture available on `127.0.0.1:55437`, from the repo:

```powershell
$env:CODEX_BRIDGE_ENABLED='false'
uv run pytest tests/test_vision_page_batch.py -k visual_dataset -q
```

This runs the real application orchestration, worker, browser and persistence
against an inert local reproduction. A deterministic fixture planner proposes
eligible IDs; no paid/live LLM is used. Assertions compare the exact 47 clicked
example IDs, reject negative targets and repeated clicks, require actual click
evidence, and check the baseline scan precedes the first click. Results go to
`flow-result.json` only after those assertions pass. This is distinct from live
button execution and does not establish business correctness of mongchiton.vn.
