# ADR-018: Visual button scope and inventory before execution

- Status: Local implementation and dataset validation.
- Date: 2026-11-01
- Supersedes the user-intent interpretation in ADR-016; historical semantic
  `buttons` scope and v2 locators remain readable.

The user means button-shaped actions on the UI, regardless of HTML tag. An
independent desktop count found 47 positions where the old filter found 15.
Explicit all-button requests now use `visual_buttons` and require worker
capability `visual-button-scope-v1`. The real accessibility role is retained;
`button_kind` separately records native, styled-link or custom affordances.
Central prompt `codex-dom-v10` uses this worker classification, retains strict
JSON constraints, excludes ordinary content links and distinguishes duplicate
UI positions. Page text cannot grant eligibility.

The worker uses generic computed presentation: compact decorated surfaces,
transparent hit areas over sprites, native/explicit button semantics, and custom
click handlers with visual affordances. Pointer styling alone is insufficient.
The dated dataset and held-out fixtures are in `benchmark/vision/visual-buttons/`.
The initial-page labels are not a whole-site/mobile coverage claim.

V3 structural descriptors identify distinct main-document button, anchor, div,
span or button-input positions without arbitrary selectors. Each observed ID
retains a live node; prepare and dispatch check node identity, fresh geometry,
classification and hit target, and require real click-event evidence. V2 keeps
its native-button grammar. A v3 proposal may be rebound after a verified complete
checkpoint restoration, with a new observation and the same descriptor; changed
checkpoints and replacement after observation/prepare remain rejected. Ephemeral
descriptors are still blocked from durable test handoff.

Visual-button readiness keeps URL, scroll, forms, semantic identities and modal
changes. Geometry and interchangeable decorative copies do not invalidate every
proposal in the batch: the exact bound target is independently verified before
clicking. Ordinary/legacy scopes retain their stronger geometric fingerprints.
Full semantics and paired screenshots remain available for outcome evidence.

The controller inventories the source page by bounded scrolling before the first
model proposal, preserving the baseline even if a later action fails. It processes
the live viewport then earlier viewports. Restore scrolls stay within 2000 pixels
per operation and must match the original checkpoint before continuing. Outbound
destinations do not expand a source-page button task into general site crawling.
No physical click is automatically retried, and no failure is converted to success.

Reports retain classification counts, label historical semantic-only scope,
and separate observed-action completion from unverified business outcomes.
Tenant authorization, evidence retention, secret redaction, approval boundaries,
provider/model, 20-call limit and cost/rate policies are unchanged. No cloud or
production service is introduced. Shared execution request/result contracts stay
v1; the v4 worker capability and v3 locator deliberately version the new behavior.
