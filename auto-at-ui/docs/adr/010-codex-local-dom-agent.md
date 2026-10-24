# ADR-010: Opt-in local Codex DOM proposal bridge

- Status: Accepted for local implementation; CLI 0.164.0 isolation qualified; synthetic live DOM canary passed
- Date: 2026-10-23
- Supplements: ADR-001, ADR-007, ADR-009

## Revision: user-authorized container isolation (2026-10-23)

Schema-delivery revision (2026-10-24): centralized prompt v6 appends the verified
response schema as data and requires a bare JSON object. The CLI no longer uses
`--output-schema`; strict local parsing, scope checks and independent browser
verification remain unchanged. A bounded diagnostic and the normal bridge both
passed the live Toggle modal canary (one call and no image each). The normal path
verified one action in 9.156 seconds. This resolves the synthetic DOM gate below;
the provider-internal cause of earlier safe stops is not established. Image
validation stays unverified/disabled, and local activation remains opt-in.

User-authorized YOLO revision (2026-10-24): `codex exec --yolo` bypasses the CLI's
inner sandbox and approval prompts within the dedicated container. Zero model
tools remain mandatory; doctor now verifies non-root/read-only-root/no-capabilities/
no-new-privileges/seccomp before qualifying the environment. Credentials remain
read-only and accessible to the trusted CLI. Prior sandbox-denial evidence is
fallback-profile evidence, not a claim about the effective YOLO invocation.
The existing model, consent gates, schema and Playwright verification are unchanged.

Historical CLI revision (2026-10-24, before v6): the user approved revising the container
pin. CLI 0.164.0 is qualified with a build-generated catalogue that removes only
three tool capability fields from bundled Luna metadata and explicitly disables
user-input tools. Probes now inspect both top-level and additional tool lists.
No tools are declared or executed. Doctor checks the catalogue against the pinned
binary, centralized v5 model instructions, filesystem/network denial and login.
JSONL still hides rejected unknown custom calls; it cannot audit every attempt.
Three bounded live DOM calls returned stop/complete, need_screenshot and
stop/no_safe_action; the separate live action gate remains unresolved.

Historical correction: the original 0.163.0 probe missed additional tool lists;
its zero-tools claim is withdrawn. See phase 07 for preserved probe history.

The user authorized a dedicated Linux container and mounting the existing Codex
credential for this job after native Windows sandbox qualification failed. This
supersedes the host-process/no-credential-mount choice below. Mount only `auth.json`
read-only into private CLI runtime storage; never include it in images, logs or
model-visible files. Qualify tool restrictions and credential-read denial using
synthetic sentinels first. Do not mount the repository, host home, Docker socket
or application credentials. Keep existing account/model and fail closed on refresh
failure. Linux process groups replace native Windows process-tree management.
Container isolation does not by itself establish credential protection from tools.

The user selected the existing host Codex login and `gpt-6-luna` for Web UI
exploration proposals. Provider ID is `codex_cli`, recipient is OpenAI. Local file
exchange does not mean offline inference. No API key, account/model fallback,
production deployment, authentication change or billing change is authorized.

Use a separate Python/uv host process on Windows with one configured trusted
tenant and one active subprocess. Mount only the explicit external spool into
local Docker containers. Never mount/copy the host credential store. The host
process must qualify command, filesystem, network and tool restrictions before
advertising readiness; read-only mode alone is insufficient. Missing capabilities
fail closed. CLI presence/login never proves model access or model quality.

Codex requires v4, explicit provider-bound DOM transfer consent and a frozen
session input policy. Screenshot transfer requires its own OpenAI permission.
HF/Gemini policies and history remain valid; no tenant is automatically enabled.
DOM is potentially sensitive: export only redacted visible role/name/type/state
and opaque element IDs, at most 100 elements, 120 characters per label and 64 KiB.
Exclude values, credentials, raw HTML and URL queries/fragments. Trusted locator
bindings stay outside the model projection and must be verified fresh by Playwright.

DB job metadata is authoritative, scoped to tenant/project/session, fence,
sequence, snapshot, input hashes and deadline. Files carry transient payloads;
they cannot authorize browser actions. Immutable policy/binding snapshots and
guarded terminal transitions prevent rewriting consent or accepting late results.
Raw payloads, prompts and CLI transcripts do not belong in durable job metadata or
activity events. Existing evidence retention and RBAC remain unchanged.

DOM and optional image calls share the session call/rate/time budget, normally
120 seconds. Screenshot escalation occurs at most once per observed state and
never follows a transport error. No automatic retries. CLI internal turns mean
process count and max_cost_usd are not strict token/dollar caps. Record actual
model, available aggregate usage and safe timings. Cancel/revoke/expire stops the
owned process tree; claimed jobs cannot silently relaunch after interruption.

Playwright remains the only browser executor, with the existing pinned worker.
Codex returns closed proposals, never commands, selectors, navigation URLs,
verdicts or approved drafts. Preserve deterministic execution contracts v1 and
human approval for generated tests. General text generation is separate.

Validate offline with fake CLI and owned PostgreSQL/browser fixtures, then report
a separately bounded synthetic live canary only after sandbox qualification.
No live inference or tenant enablement occurred in the contracts phase.
Deploy additive schema and compatible readers before enabling writers/UI. Disable
new submissions, cancel/drain jobs, stop the bridge and convert only new Codex
policy keys to an old-compatible disabled policy before parser rollback; preserve
unrelated overrides and historical evidence.
