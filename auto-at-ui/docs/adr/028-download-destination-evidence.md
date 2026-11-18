# ADR 028: Operation-bound download destination hashes

Status: implemented; isolated validation passed, 2026-11-09.

The accuracy oracle requires download initiation to reach the declared
destination or an independently reviewed redirect chain. A `download_started`
result with homepage screenshots cannot establish which URL produced the file.
Historical runs retain this missing evidence and receive no inferred credit.

For downloads already attributed by the existing executing-click guard, retain
up to eight unique SHA-256 destination hashes in that operation's private
execution closure. Emit an operation/session-bound structured diagnostic after
finalization, including status and explicit truncation. Do not export URLs,
query values, filenames, headers or file bytes. Unattributed downloads keep the
existing policy failure and cannot inherit another click's evidence.

The browser still cancels every download without retaining or executing it.
Logging failures cannot affect action outcomes. Execution v1, private transport,
model prompts and policy limits do not change. The independent benchmark reviewer
must check destination hashes against the oracle/redirect evidence, exact target
binding, completed status and retained before/after frames; a log alone is not a
pass. Missing, ambiguous or truncated evidence remains unverified.

Loop 08 confirmed that the APK endpoint adds a varying `ver` query parameter.
Independent HEAD full-URL hashes therefore cannot identify the actual browser's
redirect chain. Extend each owned-click diagnostic with up to 32 navigation
URL hashes and their observed `redirectedFrom()` parent hashes. Keep only hashes,
remove the temporary request listener when the primitive ends, mark overflow
as truncated and never change a verdict if collection/logging fails. A reviewer
must trace the actual download hash back to the declared source hash within this
operation; do not assume query differences are harmless or match by filename.
Final direct/redirect, same-page/popup, cancellation, background and logger-failure
browser matrix: 9 passed (23.2s). Strict exporter/harness/metrics: 36 passed (0.95s).

Validation covers popup and same-page downloads, query-value non-disclosure,
logging failures, background/unattributed download rejection and cancellation.
Seven browser tests passed (16.7s); 36 harness/metrics tests passed (0.73s),
including strict diagnostic scope, payload bounds and secret-field filtering.
Initial two new browser cases failed because the fixture did not recognize a
download URL containing a query; the fixture route now accepts that URL, with
the same attachment response and unchanged behavioral assertions.
