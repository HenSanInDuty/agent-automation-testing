# Phase 03 — Local file transport and Codex host process

Status: **completed**. Started: 2026-10-23 21:02 +07:00. Completed: 2026-10-24 12:31 +07:00. Dependencies: phase 1.

## Completion evidence under the authorized container revision

Latest phase 07 result (2026-10-24): v6 schema delivery passes the live DOM canary
with CLI 0.164.0 and user-authorized container-only YOLO. All three full wire
probes and offline doctor pass. See phase 07 for current evidence; the blocked
records below are historical and superseded.

Earlier phase 07 revision (2026-10-24 15:30 +07:00): user-authorized CLI 0.164.0
with immutable catalogue and centralized v5 instructions passes complete wire,
sandbox, file/locking and offline real-login doctor checks. The earlier zero-tool
claim for 0.163.0 remains withdrawn. Live action quality is independently blocked.
See phase 07 for full changed paths, commands, results and the remaining decision.

**Qualification correction, 2026-10-24:** phase 07's full wire inspection found
tools in `input.additional_tools`, missed by the original top-level-only probe.
The zero-tools claim below is withdrawn. Filesystem/mount/test evidence remains
historical; CLI tool isolation is unqualified and doctor now fails closed. See
phase 07 for the exact custom-call/JSONL reproducer and pending CLI-pin decision.

Implemented bounded atomic spool publication, integrity/scope/lease validation,
exclusive claims and consumer locks, interrupted-job no-relaunch, bounded progress,
acknowledgement/expiry/staging cleanup, fixed native invocation, stripped child
environment, output limits and Linux process-group cancellation (including shutdown
during spawn). Readiness is offline by default, bound to tenant/bridge/version and
heartbeat freshness. `doctor` performs no inference; `run` requires explicit scope
and a passing doctor. The application provider remains disabled/unwired until the
following phases. Producer/consumer production use is Linux containers sharing one
C: bind mount; native Windows execution is superseded.

Added paths:
- `apps/control-plane/application/codex_bridge.py`.
- `apps/control-plane/infrastructure/codex_bridge/{__init__,spool,process,doctor}.py`.
- `apps/control-plane/codex_bridge_cli.py`.
- `apps/control-plane/agents/prompts/codex_exploration.py` (prompt skeleton pulled
  forward for entrypoint composition; phase 04 supplies task context/validation).
- `docker/codex-bridge/{Dockerfile,container.py,qualify.py,check_mount.py,seccomp.json,SECCOMP-LICENSE,README.md}`
  and `docker/codex-bridge/fixtures/{allowed,sentinel}.txt`.
- `tests/test_codex_bridge_{spool,process,service}.py` and
  `tests/fixtures/codex_bridge_{fake_cli,tool_probe,mount_probe}.py`.

Changed paths: `.gitignore`, `.dockerignore`, `apps/control-plane/domain/ports.py`,
`apps/control-plane/domain/codex_bridge.py`,
`packages/contracts/src/auto_at/contracts/codex_bridge.py` (closed progress record),
`apps/control-plane/agents/prompts/README.md`, ADR-010 and the canonical plan README.
Existing Settings already accepts explicit absolute Linux paths; no extra secrets
or environment access was introduced outside configuration. No execution v1 change.

Validation performed:
- `docker build -t auto-at-codex-bridge:0.163.0 -f docker/codex-bridge/Dockerfile .`: passed.
- In that image, `uv run --no-sync pytest tests/test_codex_bridge_spool.py tests/test_codex_bridge_service.py tests/test_codex_bridge_process.py tests/test_codex_bridge_contracts.py tests/test_config.py -q --basetemp /tmp/bridge-tests -p no:cacheprovider --tb=short`: **108 passed**, no skips (6.64 s). Docker flags: `--rm --init --network none --cap-drop ALL --security-opt no-new-privileges --security-opt seccomp=docker/codex-bridge/seccomp.json --read-only --tmpfs /tmp:rw,nosuid,nodev,size=128m --tmpfs /bridge-home/.codex:rw,nosuid,nodev,uid=1000,gid=1000,mode=700,size=32m --workdir /app --entrypoint uv`.
- `uv run python docker/codex-bridge/qualify.py`: allowed job read passed; unrelated
  file, mounted synthetic credential, credential via `/proc`, and job write denied.
- Using the same offline container flags with `uv run --project /app --no-sync python /app/tests/fixtures/codex_bridge_tool_probe.py`: one loopback fake request,
  zero tools, unsolicited `exec_command` rejected, no synthetic marker written.
- `uv run python docker/codex-bridge/check_mount.py`: publication, synthetic result,
  acknowledgement/cleanup and two-container consumer-lock exclusion passed.
- `uv run python docker/codex-bridge/container.py doctor --auth-file C:/Users/hen/.codex/auth.json`:
  authenticated/capabilities-qualified true; configured/online false; model access
  unverified. Read-only credential mount, networking disabled, no account details
  or credential contents printed. Sandbox loopback-network denial also passed.
- Host `uv run pytest tests/test_codex_bridge_spool.py tests/test_codex_bridge_service.py tests/test_codex_bridge_contracts.py tests/test_config.py -q --basetemp .pytest-artifacts/codex-container-spool-04 --tb=short`: 84 passed before final refinements; subsequent final Linux run above covers the final source.
- `uv run ruff check .` and normal `git diff --check`: passed. Native Windows process
  and symlink-adversary cases are intentionally exercised in Linux instead.

Investigated/fixed: absent bundled bubblewrap resource during image assembly;
unsupported `tools.view_image` override (use its feature flag); `--strict-config`
not accepted by `features list` (still required on exec); `unified_exec=false`
does not disable that stable feature, so qualification relies on effective
`shell_tool=false` plus the captured empty tool list and adversarial probe. A fake
tool fixture needed stdout flushing. Windows oversized parametrization IDs were
shortened. Integrated doctor now passes after these fixes.

Deviation/limits: user explicitly authorized the credential-mounted container.
The per-container seccomp addition permits five namespace/mount syscalls needed by
rootless bubblewrap while keeping all capabilities dropped and no-new-privileges.
No daemon/host policy was changed. D: bind mounts fail on this host; C: is qualified.
Read-only auth may prevent refresh; no refresh fallback is installed. The image is
currently a local qualification image with test dependencies. No real model access,
latency, cost or live action success is claimed. Initial prompt is versioned
`codex-dom-v1`, matching the phase 01 contract; phase 04 must version behavior changes.

## Historical qualification blocker (2026-10-23 21:08 +07:00)


Superseded decision: the user has authorized a dedicated container with the
existing Codex credential mounted for this job. Resume with the README's container
revision. The Windows failures below remain historical evidence. Linux isolation
is unqualified until synthetic probes pass; phase 03 is still in progress.

Read-only inspection confirmed native Codex CLI 0.163.0 supports the planned
exec/schema/image/ephemeral/config-isolation flags. No inference, login change,
credential read/copy, or global configuration edit was performed.

Two synthetic command-only sandbox probes were run through the installed native
executable, without invoking a model:

1. `codex -c windows.sandbox=mxc sandbox --permission-profile :read-only -- cmd.exe /d /c echo CODEX_SANDBOX_PROBE`
   exited 1: `failed to prepare MXC sandbox: native MXC is unavailable on this executor`.
2. Existing elevated sandbox users are present. An explicit `codex_probe`
   permissions profile granted `:minimal` and a newly created temporary job
   directory read access, with network disabled. Both a positive-control read of
   `job/allowed.txt` and a negative-control read of sibling `outside.txt` exited 1
   before command execution: `elevated Windows sandbox requires effective :root read access`.

Only synthetic marker contents were created. This proves the tested narrow-read
profile cannot start on this host; it does **not** prove every possible Codex
configuration is unsafe. It also does not qualify a broader-read profile simply
because a shell feature can be disabled. Command/tool isolation, auth-file
protection and prompt-injection resistance remain unproven.

Official sources checked:
- [Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox): MXC
  availability and elevated/unelevated boundaries; unelevated does not support
  denied read paths.
- [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference):
  named filesystem permissions and shell-tool controls.
- [CLI reference](https://learn.chatgpt.com/docs/cli/reference): noninteractive flags.

Decision requested: use an MXC-capable Windows host, or explicitly revise the
isolation design to a separately isolated bridge environment. Keep readiness false
and do not start phases 04–07 while unresolved. No bridge service/spool/process
implementation or fake-CLI qualification is claimed complete. Safe completed
work is phases 01–02 plus this capability audit; final regression validation is
complete: 731 full Python tests, 55 browser tests, typecheck and schema parity
passed; a final isolated UTF-8 byte guard passed 53 contract tests and Ruff.
All Phase 03 acceptance tests remain due. No doctor/run entrypoint is claimed
implemented. Temporary-directory cleanup was rejected by automatic approval
review (`blocked by policy`); exact retained paths are recorded in README.

## Objective

Implement one Python host bridge using the existing signed-in Codex account, atomic local file exchange and reliable process cancellation. The CLI is a bounded proposal producer, never a browser/shell execution service.

## Exact paths

Add:
- `apps/control-plane/application/codex_bridge.py`: claim/run/complete/cancel orchestration using ports and Settings.
- `apps/control-plane/infrastructure/codex_bridge/__init__.py`.
- `apps/control-plane/infrastructure/codex_bridge/spool.py`: safe paths, atomic files, receipts and heartbeat.
- `apps/control-plane/infrastructure/codex_bridge/process.py`: fixed CLI invocation, bounded stream parsing and owned process-tree cleanup.
- `apps/control-plane/codex_bridge_cli.py`: thin local CLI composition with doctor and run commands.
- `tests/test_codex_bridge_spool.py`, `tests/test_codex_bridge_process.py`, `tests/test_codex_bridge_service.py`.
- `tests/fixtures/codex_bridge_fake_cli.py`: deterministic process scenarios with no network.

Change:
- `apps/control-plane/config.py`, `apps/control-plane/domain/ports.py`, `tests/test_config.py`.
- `.gitignore`, `.dockerignore`: ignore any repository-relative test/manual spool and CLI outputs. Default spool remains outside repository.

## Setup/readiness contract

1. All application environment/.env reads occur in Settings. Host entrypoint loads explicit bridge settings; it does not connect to PostgreSQL, Redis or browser worker. Only the control plane owns app credentials.
2. Resolve a fixed installed native executable safely. On Windows, do not concatenate job content into PowerShell/cmd strings or pass it through the npm .cmd shim as a command string. Resolve the supported native executable and validate version/path. Use argument arrays, stdin and bounded pipes.
3. Read-only doctor reports CLI version, required flags, configured root access and safe login availability. Never print auth content/account email or silently run login. The user-selected existing credential store stays on the host.
4. Run with a job-local working directory outside the repo; input includes validated prompt/context through stdin. Use fixed model, supported low reasoning/Standard setting, schema output, JSONL and ephemeral mode. Disable user config, MCP, hooks/plugins and resume behavior. Remove unrelated cloud/app secrets from child environment. Retain only OS/runtime and existing authentication requirements.
5. Qualify supported tool restrictions and the Windows sandbox before reporting ready: prompt injection must not cause arbitrary shell execution, reads of a sentinel outside the permitted job data, access to auth files by model tools, or network/tool side effects. Read-only alone is insufficient proof. Use supported CLI command policies/sandbox controls and document exact effective settings/version. If unavailable, fail doctor with `bridge_cli_unsupported`; do not use unrestricted flags or invent unsupported config switches.
6. No paid inference in doctor. Model access is `unverified` until a real bounded job succeeds; CLI presence/login is not proof of model availability. Status exposes configured/online/auth/capability/model-access states separately.
7. Heartbeat every 2 seconds with protocol/bridge/allowed-tenant/model/CLI identity; stale after 10 seconds. This is local FS-ACL trust, not a replacement public authentication protocol.

## File lifecycle

1. Producer registers metadata via application/DB before writing. Spool adapter publishes a temporary directory then renames it within the same filesystem. Fixed filenames only; request manifest includes byte lengths/hashes.
2. Derive directories from validated IDs, never model content or raw tenant names. Reject traversal, symlinks/junctions/reparse points, aliases escaping root, unexpected files, wrong ownership/scope and overlarge files. Check normalized resolved paths before every move/delete.
3. One bridge root binds one tenant and one live consumer lock. Claim a ready job atomically with exclusive creation and a claim nonce. Scope/deadline/hash checks happen before process launch. Max concurrency is one; proposed pending-queue cap is 10, rejecting excess without invoking Codex.
4. Re-read cancellation and authorization lease immediately before launch. Control plane refreshes a short authorization receipt while its session lease/policy remains valid. Missing/stale receipt prevents starting or stops an active process; its expiry cannot exceed session deadline.
5. Wrapper reads job input, builds the trusted invocation and writes raw final output only to a private temporary file. Drain stdout/stderr continuously; cap raw final output at 32 KiB, raw event line at 64 KiB and total raw stream at 2 MiB. Overflow terminates the process with a safe reason. Never preserve raw stdout/stderr as ordinary logs.
6. Allowlist events into local `events.jsonl`: sequence, timestamp, job ID, stage and bounded numeric usage. No model reasoning, tool command, assistant prose, credentials or response text. Persist at most 64 stage records per job; coalesce repeated progress. Unexpected tool execution events abort, in addition to preventive sandbox restrictions.
7. Validate exit code, successful terminal event, final schema, model provenance and output identity before atomically publishing `response.json`. Nonzero exit with a plausible output file is still a failure. Phase 4 performs semantic proposal validation too.
8. Cancellation, expired deadline or lost authorization heartbeat stops the owned process tree. Use a tested Windows process group/job-object mechanism so child descendants do not survive; POSIX cleanup only if explicitly supported. Stop only processes spawned by this bridge. Emit cancellation receipt and discard partial/late results.
9. At most one CLI launch per job. Restart may consume a fully committed valid response; a claimed/running job with unknown process outcome is marked interrupted, never silently re-launched. A new user exploration has a new session/job.
10. Delete job payloads after consumer acknowledgement, terminal cancellation or expiry. Keep durable metadata in DB, not raw spool history. On startup reconcile abandoned directories and clean expired payloads only under verified root; do not remove active jobs or follow links. Failed cleanup is observable and keeps sensitive bytes inaccessible to other users.
11. App/host shutdown and disk-full/ACL failures are explicit safe failures, with no Gemini fallback and no browser replay.

## Schema/operational impact

Files implement phase 1 contracts; no new public network endpoint. The opt-in Compose bind mount is installed in phase 7. Files are transient; request/response identity plus DB fence prevents reuse, while filesystem ACLs establish local actor trust. Never claim shared-machine multi-tenant security from paths alone.

## Tests and validation

- `uv run pytest tests/test_codex_bridge_spool.py tests/test_codex_bridge_process.py tests/test_codex_bridge_service.py tests/test_config.py -q`
- `uv run ruff check .`
- Read-only host smoke: `uv run python apps/control-plane/codex_bridge_cli.py doctor`.

Fake scenarios: success, login/model/quota failure, malformed/partial JSONL, nonzero exit, excessive output, hanging process, child process, cancellation during startup/output, duplicate consumers, partial writes, old result, invalid hash, wrong tenant, clock/deadline expiry, stale producer heartbeat, disk full and unsafe paths. Use synthetic sentinel secrets, never actual credentials. Test atomic publication/locking and process-tree termination on Windows and on the chosen Docker Desktop bind mount.

Acceptance: one launch per job, no child remains after cancellation, no unsafe logs or outside-root writes/deletes, and readiness never claims unavailable sandbox/model features. Tests must inject the fake CLI and prevent real codex execution.

## Non-goals

No API-key fallback, billing changes, Windows service installation, global Codex configuration edits, credential copying or arbitrary command/job execution. If the installed CLI fails qualification, report that limitation and keep the provider disabled.
