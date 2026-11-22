# ADR-019: Revalidate delayed DOM proposals against fresh browser evidence

Viewport discovery is subsequently separated from model actions in
[ADR-020](020-deterministic-viewport-discovery.md).

- Status: Accepted for local implementation at the user's request.
- Date: 2026-11-05
- Extends ADR-014 and ADR-015.

Mongchiton's JavaScript carousel changes interaction geometry every three seconds.
The model completed successfully, but the whole-viewport post-response comparison
discarded its result. Reduced motion does not stop this JavaScript autoplay.

For a successful DOM-only reply consisting entirely of bound click/type targets,
allow one read-only refresh and fresh DOM observation within the existing step,
state and hop limits. The browser worker must verify the same Page, URL, scroll,
form structure and private form values, visible landmarks/dialogs/headings, and
the original live node for every proposed target. Compare its descriptor,
semantic identity, destination and ancestor context; ground it again to verify
visibility, uniqueness, enabled/editable state and occlusion. Geometry comes from
the new observation. Old element IDs may be mapped only after this verification;
snapshot IDs, checkpoints and screenshot evidence are always new. Changes to any
proposed target reject the batch. Private comparison material remains in RAM.
After a verified checkpoint restoration through document navigation, existing
semantic-descriptor rebinding remains supported. Within the same document, an
identical replacement node is rejected; anonymous structural bindings remain
strict across navigation as before.

This narrows ADR-015's blanket rejection of post-call drift: it does not retry the
model, reuse coordinates, repeat physical actions or relax prepare/execute state
guards. Image-stage replies, unbound actions, scroll/stop decisions, failures and
malformed outputs still fail closed. Persist revalidation success/rejection as an
activity event; preserve the original model job and its original observation.
Wait for the rate slot before collecting DOM evidence, then recheck state before
consuming a model-call reservation. Ground up to four independent DOM candidates
concurrently, retaining document order and the same byte/element limits and final
state checks. This shortens observation time without accepting unstable captures.

Provider/model, prompts, data consent/redaction, rate/cost limits, tenant fencing,
retention, approval before generated-test execution and historical results stay
unchanged. TestExecutionRequest/TestExecutionResult remain unchanged. The optional
private worker observation fields require a compatible controller/worker rollout;
older workers reject them rather than silently accepting an unverified proposal.

Validation covers real Chromium carousel drift, moved/replaced/renamed targets,
destination changes, disabled/covered controls, form changes, modal/heading/ancestor
context changes, scrolling, navigation and fencing; application tests verify one
model call and fresh bindings, fail-closed cases, policy revocation and rate waits.

Follow-up on 2026-11-08: the final live trial from 2026-11-06 stopped during a
read-only refresh, before its next model call. The worker recorded
`settle_timeout` (800 ms quiet required, only 288 ms observed within 3 seconds),
but the controller replaced that reason with `state_mismatch`. Preserve the
worker's safe failure code. Refresh uses the same 10-second readiness ceiling as
navigation/scrolling, capped by the existing operation deadline, with the same
800 ms quiet requirement. This is a bounded opportunity for delayed content to
settle, not an exemption for changing controls. Continuously unstable pages still
stop without a click or new checkpoint. No model retry or increased call budget
is introduced.
