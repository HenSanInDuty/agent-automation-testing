# ADR 035: Refresh a known popup after a rejected preparation

Status: implemented; focused validation passed, 2026-11-18.

Round 18 stopped at close-popup operation 41: form presence and values changed
between the retained before-frame and final preparation validation. The worker
rejected preparation before dispatch. Existing bounded recovery recognized only
the later before-dispatch rejection, so it could not observe this hydrated popup
and prepare a new close against its current state.

Extend that recovery using positive transport evidence: a rejected restore
close-popup, explicit `dispatch_started=false`, prepare failure stage, matching
retained before-frame and known child page, `state_changed_during_prepare`, no
after-frame/page and `action_not_executed`. Missing or contradictory evidence,
legacy transport, unknown outcomes and dispatched operations do not qualify.
The existing before-dispatch path remains supported with its own evidence shape.

Recovery observes the same known child and prepares a new close, at most twice
within the original shared deadline and state/hop limits. It preserves every
rejected operation, the parent checkpoint, private-form guards and child-parent
identity checks. It never replays the original click or infers success from a
rejected action. Contracts, prompts, model, oracle and policy limits are unchanged.

A loopback-only integration fixture mutates a hidden form after the real before
capture. The original application fails this reproduction. Cases cover one-time
and persistent drift, missing/unknown dispatch evidence, wrong child and exhausted
state/hop limits. Pure rule tests separately exercise contradictory evidence.

Also add allowlisted timing telemetry to ADR-034's optional local outcome sample:
stage, fixed outcome, durations, budget and correlation IDs; reuse logs expose
only a boolean and sample age. No page content, URLs, form values or raw errors
are logged. A capture-timeout fixture verifies fallback. A read-only production
worker probe measured inspect-state calls at 114–703 ms and PNG capture at 427 ms;
this motivates measurement, not an increased budget or a claim of carousel repair.
The 500 ms sampling budget and all fallback decisions remain unchanged.


Round 19 completed 21 popup closes with no preparation rejection: the new branch
was not exercised live. It failed the frozen accuracy ceiling (46/49); qualification
remains pending. Timing isolated 16 screenshot timeouts, five settle deadlines and
two verification deadlines among 23 optional samples, with zero reuse. See
`benchmark/vision/accuracy/ROUND19-20261118.md` for evidence and validation scope.
