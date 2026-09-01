# Phase 2 — Verified visual evidence and Hugging Face adapter

## Objective

Make one verified screenshot available to a Hugging Face multimodal model under
the Phase 1 policy without expanding the existing redacted evidence boundary.

## Scope and prerequisites

- Phase 1 contracts/policy and a pinned candidate model for the development
  evaluation environment.
- Existing artifact records/readers in `apps/control-plane/agents/shared/evidence.py`
  and persistence/artifact infrastructure.

## Execution record

**Status:** completed — 2026-08-31 18:19 ICT

The approved development model is `Qwen/Qwen2.5-VL-7B-Instruct`. This phase
will use mocked provider calls only; its live benchmark and rollout evaluation
remain Phase 5 work.

## Completion record

- Added `agents/vision/evidence.py` for tenant/run/session-scoped, bounded,
  signature-checked PNG/JPEG reads that return bytes only transiently.
- Added prompt framing, schema validation, and a one-shot no-fallback executor;
  all provider, timeout, malformed-output, and policy failures become safe
  advisory `unavailable` results.
- Extended the existing OpenAI-compatible adapter solely with injectable HTTP
  transport for mocked multimodal request verification; credentials remain in
  `Settings` and no payload is logged or persisted.
- Validation passed: focused Ruff plus 25 focused pytest cases, including the
  existing agent-boundary suite.

## Exact paths and changes

- Add `apps/control-plane/agents/vision/evidence.py` with a narrow
  `VerifiedScreenshotReader` port.  It may read only a tenant/run/session-scoped
  screenshot artifact, checks checksum/content type/declared size, enforces
  `max_screenshot_bytes`, decodes only an allowlisted image type, and produces
  bytes transiently in memory.
- Keep `agents/shared/evidence.py` reference/redaction semantics unchanged;
  add tests ensuring its existing bundles never suddenly contain image bytes.
- Add `apps/control-plane/agents/vision/executor.py` and `service.py` to build
  a hostile-content-aware prompt, attach the screenshot as an OpenAI-compatible
  image message to `LanguageModel.ainvoke`, parse only the Phase 1 action schema,
  and convert malformed/provider/timeout responses to a safe unavailable
  outcome.
- Extend `apps/control-plane/agents/shared/openrouter.py` only to serialize an
  approved multimodal chat payload through `huggingface_base_url`; do not add
  a browser, SDK credential, or provider selection into domain/application
  code.  Keep API keys in `Settings`.
- Reuse/extend `AgentStepGuard` rather than introducing unbounded retries.
  Implement one-shot primary invocation with configured timeout, byte/token
  accounting, no fallback unless an explicitly approved Hugging Face fallback
  exists, and no model output logging.
- Add prompt/model/evidence checksum, policy version, latency, safe status,
  correlation ID, and model name to provenance/activity metadata.  Do not
  persist request payloads, screenshot bytes, OCR text, or signed URIs.

## Data flow

1. Workflow obtains a verified screenshot reference created by the isolated
   worker.
2. The evidence reader verifies tenant/session ownership and reads bounded raw
   bytes into memory.
3. The executor sends the image plus a minimal task/objective to the configured
   Hugging Face vision model, instructing it to treat page content as data and
   return only an action candidate or `stop`.
4. The executor validates coordinates/action parameters and stores only a
   proposal plus checksums/provenance.  Bytes are released after the request.

## Tests and validation

- Add unit tests for wrong tenant/run, checksum mismatch, oversize/non-image
  rejection, no raw URI/body in log/proposal serialization, injection-resistant
  prompt framing, action-schema rejection, timeout, and unavailable fallback.
- Add a mocked HTTP test proving Hugging Face receives a multimodal request
  only after consent/policy guards succeed.
- Run `uv run pytest tests/test_agent_boundaries.py tests/test_vision_evidence.py tests/test_vision_executor.py`.

## Acceptance criteria

- A permitted screenshot reaches only the configured Hugging Face endpoint in
  transient form; every durable record is safe metadata/provenance.
- Failure to read or interpret a screenshot is advisory/unavailable and never
  changes a test result.

## Risks and non-goals

- Raw-image consent does not imply permission to send trace, DOM, credential,
  or network payloads.  OCR/redaction is intentionally not claimed in this
  phase because raw transfer was selected.
