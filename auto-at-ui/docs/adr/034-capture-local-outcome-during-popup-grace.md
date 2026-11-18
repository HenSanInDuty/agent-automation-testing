# ADR 034: Capture local click outcomes during popup observation

Status: implemented; focused and regression checks passed, 2026-11-17.

Round 17 operation 26 selected carousel indicator 4, but its retained after-frame
showed indicator/slide 5. The frozen oracle cannot credit that result. The verified
physical target does not establish the intended outcome; autoplay/capture timing
was a hypothesis. A synthetic carousel now reproduces loss of slide 4: the old
worker waits 500 ms for an unexpected popup, then settles and captures slide 5.

For a verified v3 DOM click in visual-buttons scope with no expected popup,
download or source navigation, observe an optional local outcome concurrently
with the existing 500 ms popup grace period. Within that same bounded window,
require normal readiness and quiet-state checks, capture pixels and compare the
bracketing states. Keep at most one size-bounded sample in memory; do not persist
it or create another operation at this stage. Failure simply discards the sample.

After the unchanged popup/download reconciliation and final settle, reuse the
sample only for the same page/document, with the original target still connected
and equivalent current interaction/URL/scroll/form state. Passive visual changes
use the existing equivalence rule; no fingerprint policy is relaxed. Preserve the
sample's actual capture timestamp and bind the checkpoint to its observed state
and pixels. A late popup, navigation (including same-URL reload), target replacement,
form/control drift, failed action or failed sample uses the normal final capture.

This changes observation timing, not website behavior: no autoplay suppression,
clock manipulation, click retry, new model call or outcome-success inference.
The 500/8000 ms popup windows, step/session deadlines, exact-node dispatch guards,
private-form checks and origin policy remain. The original checkpoint and runner
contracts are unchanged; a completed operation still needs independent review.

Tests use a synthetic slide advancing after click, checksum-bound capture records,
and exact-once click assertions. Negative cases cover changed forms, disabled
controls, target replacement, delayed popup, same-URL navigation and capture
failure. Live qualification remains separate and must restart for the new source.

Round 18 did not qualify. All six carousel after-frame timestamps were 1111–1552 ms
after confirmed click, outside the early-sample budget. This indicates fallback
capture rather than successful reuse; the exact rejection/timeout stage is not
instrumented. Indicator 3 still has slide 4 in its retained after-frame. The
lightweight synthetic success does not establish live effectiveness. A subsequent
iteration must measure the sampling stages and reproduce realistic DOM-read
latency before revising the strategy, without merely increasing policy limits.
The separate terminal failure was form presence/value drift during preparation
of a close-popup operation; that action never uses early local click sampling.
