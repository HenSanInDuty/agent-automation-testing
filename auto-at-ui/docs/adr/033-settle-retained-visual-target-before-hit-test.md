# ADR 033: Settle the retained visual target before hit testing

Status: implemented; 102 worker regressions passed, 2026-11-17.

Live round 15 reached 46 positive oracle bindings in 49 click attempts. One
additional completed click opened the video from a different carousel DOM copy;
two later video-copy proposals were rejected (`unsupported_target` and
`stale_dom_target`). The frozen oracle and all rejected attempts remain unchanged.
The run cannot qualify: even every completed positive binding being correct gives
an accuracy upper bound of 46/49. Its final unsafe restoration is a separate issue.

A synthetic moving target reproduces the first rejection: after the before-frame
capture, the retained node moves between geometry sampling and point hit testing.
Recomputing the center alone is insufficient. For v3 DOM bindings, wait for that
exact retained element to become stable after capture, bounded by the smaller of
one second and the existing operation timeout. This is a read-only wait; it does
not scroll, click, retry an operation, freeze animation or adopt a new element.

After the wait, verify the original live node, full original snapshot state
(including private forms), and that the descriptor still resolves to that same
connected node. The existing grounding, end-of-prepare and dispatch guards remain.
Continuous animation, replacement or changed form state must reject without a
physical action. Legacy v2 and semantic descriptor behavior stays unchanged.
No prompt, policy cap, transport or execution-contract change is needed.

Focused reproduction: three failures before the change; three passes after it.
The positive case clicks exactly once after motion ends. Negative cases mutate
a private form or replace the target at animation completion. A bounded
continuous-animation case is included in the final matrix. Live effectiveness is
not established by the fixture; the next iteration retains the same oracle.

Final matrix: 102 passed (6.2m); worker typecheck, Ruff, generated contract and scoped diff checks passed.
