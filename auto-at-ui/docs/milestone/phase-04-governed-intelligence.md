# Phase 4 — Governed intelligence

**Status:** planned  
**Prerequisite:** Phase 3 complete and approved LLM/data-governance ADR  
**Exit:** triage and healing produce evaluated, redacted, auditable proposals
that cannot alter a verdict or source without named human approval.

## Checklist

- [ ] Approve LLM/provider, permitted data classification, model/prompt
  versioning, rate limits, token/cost budget, evaluation data, and fallback.
- [ ] Implement recursive redaction for headers, cookies, query/form/JSON data,
  URLs, logs, and evidence metadata; store policy version and input hash.
- [ ] Normalize worker evidence into a bounded typed `EvidenceBundle`; keep raw
  binary evidence in artifact storage only.
- [ ] Define `TestIntent`, `TaskSpecification`, triage result, and
  `HealingProposal` schemas with provenance, confidence, evidence references,
  and stop conditions.
- [ ] Implement advisory, schema-validated triage for product/test/environment/
  flaky categories; never change run status.
- [ ] Implement ranked healing proposals only; grant no source write, merge,
  shell, database, or browser-profile authority to the agent.
- [ ] Implement immutable approve/reject API, reviewer identity, reason, audit
  event, and approved-change review-branch flow.
- [ ] Require an independent deterministic rerun before promoting locator
  knowledge or episodic memory.
- [ ] Test redaction, budget exhaustion, provider outage, approval enforcement,
  and false-healing rejection.

## Completion demonstration

A failed run produces a redacted proposal. Without approval—or with an LLM
failure—the deterministic result remains unchanged. An approved healing is valid
only after deterministic rerun validation.

## Validation

Python/evaluator fixtures, redaction/security tests, and failure-to-proposal-to-
approved-rerun integration test.
