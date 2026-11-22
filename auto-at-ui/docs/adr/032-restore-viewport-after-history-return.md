# ADR 032: Reconcile the viewport after a history return

Status: implemented; isolated regressions passed, 2026-11-17.

Iteration 14's checkpoint diagnostics locate a restoration failure after the
homepage news link. The queued target checkpoint was at y=0; Back returned the
homepage at y=576. URL and private form comparison matched while interaction
and scroll did not. The controller only reconciled scroll before attempting
Back, when the current URL was still the news page. Two later observations
could not fix that viewport difference and replay correctly remained forbidden.

Reuse the existing bounded reversible scroll reconciliation after each fresh
post-Back observation. Require the observed target Page, exact URL fingerprint
and matching horizontal scroll; retain existing delta/chunk bounds. Verify the
complete original checkpoint after scrolling, including private form values,
before any queued action. Do not repeat Back or click, replace checkpoints,
release old proposals, or treat URL/scroll equality as sufficient restoration.

The synthetic saved-history fixture sets manual scroll restoration and returns
the same document at a different viewport. Red validation stops at unsafe replay
and misses its sibling. A variant with changed hidden form values must remain
blocked even after scrolling. Existing popup/history/mutation regressions are
required. No execution v1, private transport, prompt, policy or provider changes.

Red `42c3aa9abfdf`: one expected unsafe-replay failure and one passing form-drift
negative. History matrix `87faf65ba9cb`: 11 passed. Final `129f7aab9295`: six
passed, including both scroll directions, form drift, panel ordering, popup
hydration and exact-node replacement. Ruff, worker typecheck and generated
contract checks passed. Live accuracy still requires measurement.
