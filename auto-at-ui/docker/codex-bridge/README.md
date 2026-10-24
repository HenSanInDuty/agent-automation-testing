# Local Codex bridge container

**Isolation qualified; synthetic live DOM canary passed (2026-10-24).** The user
approved revising the container pin to 0.164.0. Its bundled Luna metadata forces
Code Mode despite feature flags. The build generates a fixed model catalogue,
changing only `tool_mode`, `apply_patch_tool_type` and `experimental_supported_tools`.
All other bundled metadata stays intact. `tools.experimental_request_user_input`
is also explicitly disabled. Full wire probes inspect both declaration surfaces
and report zero tools; injected calls execute nothing. Rejected unknown custom
calls remain hidden in JSONL, which is not a complete attempt audit.

`codex-dom-v6` uses a build-generated model-instructions file from the centralized
prompt module. Doctor checks both immutable files against their source before
checking authentication. Missing or altered files fail closed. The verified schema
is appended to the prompt instead of using CLI `--output-schema`; output still
must pass strict local validation. The normal live DOM canary now verifies one
action in 9.156 seconds, with one call and no image. Tenant activation remains
explicit and opt-in; live image behavior remains unverified and disabled.
The native host CLI and existing login are unchanged.

This is the user-authorized replacement for the native Windows bridge. It uses
Codex CLI 0.164.0 with the existing ChatGPT login and pinned `gpt-6-luna`. Only
`auth.json` is mounted, read-only. Authentication contents are never printed,
copied into an image, or returned to model tools. A read-only auth mount may
prevent token refresh; refresh failures stop the job without modifying host login.

Build from the repository root:

```powershell
docker build -t auto-at-codex-bridge:0.164.0 -f docker/codex-bridge/Dockerfile .
uv run python docker/codex-bridge/qualify.py
uv run python docker/codex-bridge/check_mount.py
uv run python docker/codex-bridge/container.py doctor --auth-file "$env:USERPROFILE/.codex/auth.json"
```

The user-authorized invocation is `codex exec --yolo`, inside this container only.
CLI approvals and inner sandboxing are bypassed. Doctor requires non-root,
read-only root, zero effective capabilities, no-new-privileges and seccomp. The
model's tools remain unavailable. Authentication is accessible to the trusted CLI;
read-only mounting prevents writes, not reads by arbitrary container processes.

Doctor runs with networking disabled. It checks the exact CLI version/flags,
effective disabled features, allowed job reads, denied unrelated/credential/proc
reads, denied writes and denied sandbox loopback connections in the fallback
profile only; those are not effective YOLO restrictions. It checks the login
type without printing identity or tokens. It never infers that model access is
available. `configured=false` is expected until a tenant and bridge are configured;
`online=false` is expected until a consumer is running.

The application integration uses the [opt-in Compose overlay and runbook](../../docs/codex-local-bridge.md).
Do not enable a tenant based solely on a doctor pass. For standalone diagnosis,
the explicit launcher accepts:

```powershell
uv run python docker/codex-bridge/container.py run `
  --auth-file "$env:USERPROFILE/.codex/auth.json" `
  --spool "C:/Users/<user>/AppData/Local/AutoAT/codex-jobs" `
  --bridge-id "<configured-bridge-uuid>" --tenant "<configured-tenant>"
```

The spool must already exist with access restricted to the trusted local user and
the local Docker deployment. Use one tenant and one consumer per root. This
Docker Desktop instance can bind C: but currently rejects D: mounts with `no such
device`. Both application producer and consumer must run in Linux containers
sharing that same mount; Windows/Linux advisory lock interoperability is not
claimed. The mount probe verifies publication from Windows, a Linux synthetic
consumer response, acknowledgement cleanup, and exclusion between two Linux
consumers. It uses no credentials or real model. Docker `--init` reaps orphaned
children; cancellation kills the bridge-owned Linux process group.

The launcher uses a non-root UID, all capabilities dropped, no-new-privileges,
read-only image filesystem, bounded memory/PIDs and temporary runtime directories.
It mounts neither host home, repository nor Docker socket. The run mode permits
the CLI's provider connection. With YOLO there is no inner command sandbox;
zero callable model tools are required, and the outer container is the boundary. The
current qualification image includes locked development dependencies and synthetic
tests; production/multi-tenant deployment is outside this plan.

## Seccomp provenance

`seccomp.json` derives from the Moby default at
[`4b8214fc4971e06172938a1f1554ccff6647ee80`](https://github.com/moby/profiles/blob/4b8214fc4971e06172938a1f1554ccff6647ee80/seccomp/default.json),
under the accompanying Apache 2.0 `SECCOMP-LICENSE`. The only policy addition is an
allow rule for `clone`, `unshare`, `mount`, `umount2`, and `pivot_root` so rootless
bubblewrap can construct its nested namespaces. All other Moby rules remain.
This is per-container; no daemon policy, host sysctl, host account or global Codex
configuration was changed. The default Docker profile failed the positive control
before sandboxed commands could run. This profile is not a general-purpose host
security guarantee or a reason to add privileged mode, SYS_ADMIN or host mounts.

## Offline evidence

The fixture `tests/fixtures/codex_bridge_tool_probe.py` uses only a loopback fake
Responses endpoint in a `--network none` container, without credentials. It now
counts declarations in both `tools` and nested `input.additional_tools`, supplies
an unsolicited `exec_command` or `--custom-call` Code Mode call, and checks a
synthetic marker. `--valid-response` checks structured response parsing separately.
The previous zero-tools conclusion inspected only the top-level list and was
incorrect. All three modes now exit 1 for the remaining tool declarations.
The custom call is denied by the disabled host but hidden from JSONL. CLI metadata accepts a fixed model;
the phase 07 canary now receives valid Luna responses and usage through the existing
login, but returns `stop/no_safe_action` without a verified browser action. See the
[evaluation record](../../benchmark/vision/codex/README.md). The default stays disabled.

References: [OpenAI credential storage/headless authentication](https://learn.chatgpt.com/docs/auth),
[OpenAI configuration](https://learn.chatgpt.com/docs/config-file/config-reference),
[Docker seccomp profiles](https://docs.docker.com/engine/security/seccomp/).
