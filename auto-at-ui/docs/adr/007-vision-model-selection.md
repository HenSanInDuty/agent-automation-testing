# ADR-007: Pin the local vision-agent evaluation candidate

- Status: Accepted for local evaluation only
- Date: 2026-08-31

## Context

Visual exploration needs a multimodal model through the existing Hugging Face
OpenAI-compatible gateway. Raw screenshots are sensitive and the feature is
advisory, tenant-opt-in, and disabled by default. A mutable model branch cannot
support repeatable benchmark results or incident rollback.

## Decision

Use `Qwen/Qwen3.8-27B` for the local evaluation candidate, pinned to Hugging
Face revision `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0` (observed
2026-09-01), routed through the explicitly approved `deepinfra` provider. It
supersedes the unavailable Cohere and Qwen/Novita routes. The
deployment endpoint must resolve that exact revision before a tenant policy is
enabled. Record this model ID, revision, fixture dataset version, and the
endpoint/provider identity in every benchmark report.

The configured default remains disabled. The model may propose one
schema-validated action only; Playwright determines test verdicts and human
approval remains required before a generated test revision can run.

## Consequences

- An evaluation-only Hugging Face credential or approved mock endpoint remains
  required before any endpoint-backed benchmark or canary. No provider call was
  made to make this decision.
- If the selected endpoint cannot serve the pinned revision and remote-image
  input using the OpenAI-compatible `image_url` adapter, leave vision disabled and
  use the approved mock endpoint for evaluation until an adapter change is
  separately approved.
- Production rollout, data region, retention, or paid use remains outside this
  ADR and requires separate approval.
