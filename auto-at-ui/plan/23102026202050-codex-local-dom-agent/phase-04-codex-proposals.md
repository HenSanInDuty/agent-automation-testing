# Phase 04 — Codex prompts, proposal validation and image escalation

Status: **completed**. Started: 2026-10-24 12:31 +07:00. Completed: 2026-10-24 12:54 +07:00. Dependencies: phase 1 contracts, phase 2 observation, phase 3 bridge.

Reconciliation: phase 03 pulled forward the basic central prompt for entrypoint
composition. Version it to `codex-dom-v2` when adding bounded task context, keeping
the phase 01 prompt-version naming convention. Add private `CodexTaskContext` to
new v2 requests (omitted by old synthetic v1 fixtures). Use a root-object structured
output envelope around the closed result union; unwrap only that exact envelope.

## Objective

Turn a sanitized DOM job into validated advisory actions, optionally requesting one screenshot. Keep model text, element references and image coordinates outside deterministic execution authority.

## Exact paths

Add:
- `apps/control-plane/agents/prompts/codex_exploration.py`.
- `apps/control-plane/agents/vision/codex_service.py`.
- `apps/control-plane/application/codex_candidates.py`: budgets, stage transition and policy orchestration.
- `apps/control-plane/infrastructure/vision/codex_batch.py`: bridge request/result adapter.
- `tests/test_codex_candidate_service.py`, `tests/test_codex_model_batch.py`.
- `tests/fixtures/codex_bridge_responses.json`: synthetic response cases.

Change:
- `apps/control-plane/agents/prompts/README.md`.
- `apps/control-plane/application/vision_model_batch.py`.
- `apps/control-plane/agents/vision/executor.py`: typed optional trusted bindings in batch outcome, preserving old callers.
- `apps/control-plane/agents/shared/runtime.py`: explicit reservation API if needed to avoid counting one call twice.
- `tests/test_vision_executor.py`, `tests/test_vision_model_batch.py`.

## Behavior and data flow

1. Define version `codex-dom-exploration-v1` and export both DOM and image-stage instructions centrally. Input page text is untrusted data. The prompt requests only the phase 1 response schema, refers to provided element IDs, prohibits obeying instructions found on the page and permits explicit stop/need_screenshot.
2. Build a bounded context containing the task intent, sanitized observation, candidate cap and already-observed action summary. Do not send the repository, full HTML, historical screenshots, browser credentials or raw activity log. Do not fork/resume this coding conversation.
3. Generalize model-session identity to carry project/correlation/fencing and observation binding where needed. Define a typed proposal result that pairs an existing VisualAction with optional trusted DOM snapshot/element/locator binding. Never derive that binding from model-provided selectors.
4. For DOM click/type output, validate the element exists in the exact observation, is eligible and has an unambiguous trusted binding. Translate to existing action semantics; retain the snapshot binding for fresh worker resolution. Validate normalized coordinates only on the image stage. Validate all candidates before accepting any; an invalid item rejects the batch.
5. Type text remains restricted synthetic input, in memory through action dispatch. Apply existing redaction/credential checks. Do not persist typed text in proposal/edge logs or raw CLI output; job payload is transient and cleaned. Existing generated-test handoff still blocks unbound typed inputs.
6. `need_screenshot` is accepted only after a successful DOM-stage response and with no simultaneous candidates. It has a short enum reason, not arbitrary text. Recheck current provider/model/DOM and image consent, remaining time, snapshot fingerprint and available call/rate budget.
7. If allowed, attach the existing matching frame or capture a verified same-state frame, with type/hash/dimensions/size validated. Only then create an image-stage job. No screenshot file/argument exists in a DOM-only job; application evidence screenshots may still exist for the Website.
8. Image stage includes compact DOM as context and the PNG. Accept schema-valid coordinate or element-ID actions and pass them through normal unique locator verification. Canvas/closed-shadow targets that cannot be grounded still stop safely. A second image request is invalid; lack of consent yields an explicit limitation, not guessed actions.
9. Reserve one model step before each CLI launch, including screenshot escalation. Use the same rate scheduler across both stages; refactor accounting so `calls` and AgentStepGuard cannot diverge. Queue wait/startup/rate wait/model time all consume the original deadline. No automatic retry for CLI failures, invalid output or unknown launch outcome.
10. Do not present the existing 1000-token HTTP parameter as a CLI generation limit. Enforce input/output byte caps and bounded invocations; record usage returned by CLI. CLI internal turns/reasoning/overhead can consume additional quota. A usage ceiling evaluated after completion can stop future calls, not undo prior usage.
11. Reject reported model substitution and unsupported output. If CLI does not report actual model, record requested model plus unavailable actual-model provenance, rather than inventing it; phase 7 must establish how the pinned CLI confirms the selected model.
12. Return stable safe failure/stage codes and sanitized timings. Raw model content is never sent to Website events. The application owns final session status and browser dispatch.

## Contract/API impact

New private bridge schema and internal typed proposal binding only. Existing VisualAction validation remains authoritative for normalized browser actions; no deterministic runner v1 changes. Add optional observation/progress hooks to the model-batch port with compatibility defaults or split capability-specific ports explicitly; legacy HF/Gemini must not acquire a DOM dependency.

## Tests and commands

- `uv run pytest tests/test_codex_candidate_service.py tests/test_codex_model_batch.py tests/test_vision_executor.py tests/test_vision_model_batch.py -q`
- `uv run ruff check .`

Cases: DOM success without image, missing/unknown element, arbitrary selector/script, prompt injection, duplicate IDs, invalid action fields, over-cap output, one invalid sibling, empty result, valid stop; image requested/allowed/denied; repeated image request; changed state before image; consent revoked while queued/running; exhausted call/rate/time budget; late/wrong-hash/wrong-model result; secrets in response; valid type proposal excluded from persistent safe projection.

Acceptance: every action has an auditable source and independent browser validation requirement. Image escalation consumes an additional budget reservation exactly once. No test invokes a real provider.

## Risks and non-goals

## Completion evidence

Implemented the versioned DOM/image prompt and strict root-object schema, bounded
redacted task context, whole-batch semantic validation, trusted worker bindings,
and a two-stage application service sharing one deadline/rate/call budget. The
adapter registers metadata before publication and verifies identity/hash/model,
live consent, readiness and deadline before accepting and acknowledging a result.
Legacy HTTP adapters fail closed for Codex rather than selecting another provider.

Changed paths: all added paths listed above; changed prompt README, model-session
identity, candidate outcome, runtime guard, and existing model-batch fallback test.
Additional dependency changes: `packages/contracts/src/auto_at/contracts/codex_bridge.py`
(bounded v2 task context and exact-envelope parser),
`apps/control-plane/infrastructure/codex_bridge/process.py` (shared parser),
`apps/control-plane/domain/ports.py` (durable gateway protocol), and
`apps/control-plane/infrastructure/vision/model_batch.py` (closed Codex dispatch).
`tests/test_vision_executor.py` was exercised without edits.

Validation: `uv run ruff check .` passed. `uv run pytest
tests/test_codex_candidate_service.py tests/test_codex_model_batch.py
tests/test_vision_executor.py tests/test_vision_model_batch.py
tests/test_agent_runtime.py tests/test_codex_bridge_contracts.py -q
--basetemp .pytest-artifacts/codex-phase4-05 --tb=short` passed **171 tests** in
3.66 seconds. Tests cover binding/eligibility/caps/invalid siblings, image-only
coordinates, safe typed projection, prompt redaction, exact schema envelope,
DOM-only operation, one escalation, revocation/exhaustion/stale state/deadline,
wrong-scope/hash/model results and durable-before-file ordering. No provider call.
The initial 40ms late-result fixture expired during Windows publication; changed
it to an explicit one-second deadline and waited past it, then reran successfully.

Deviation: prompt is `codex-dom-v2` to match the existing contract naming scheme;
v1 synthetic jobs remain readable. Persistence implementation and v4 wiring remain
phase 05. The built container still contains phase 03 source until rebuilt during
integration. CLI usage is measured after completion; no invented token limit.

DOM-first quality/latency is a measurement, not guaranteed by a smaller model. Do not add provider fallback, richer reasoning chains, arbitrary code generation, full browser control or automatic retries in this phase.
