# ADR-037: Claude Code (`claude -p`) as a second local bridge engine

Status: accepted (user direction 2026-11-19). Date: 2026-11-19.

## Context

The accuracy loop (rounds 01-20) ran only `codex_cli / gpt-6-luna` through the
DOM-first local bridge. The user asked to compare Claude on the same task and to
run Claude through `claude -p`, not the Anthropic API. A screenshot-only Claude
adapter would change both the model and the input mode, making a comparison with
Codex uninterpretable.

## Decision

- Add provider `claude_cli` pinned to `claude-opus-5-5`. Contracts now name a
  bridge provider (`codex_cli` | `claude_cli`) with exactly one model each; DOM
  and image consent, requests and responses must name the same provider.
- The bridge selects one engine (`CODEX_BRIDGE_ENGINE=codex|claude`). The Claude
  engine runs `claude -p` in a dedicated hardened container (same user, read-only
  root, no capabilities, seccomp, egress-only network) with all Claude Code tools,
  MCP, settings and persistence disabled; only StructuredOutput is permitted.
- Prompt, schema, validator, guards, oracle and policy limits are shared and
  unchanged. Draft generation remains Codex-only.
- Credentials: only a short-lived access token file is mounted; no refresh token
  or application secret enters the container.
- The earlier same-day Anthropic API screenshot adapter was removed.

## Consequences

- Changing the model resets the qualification streak; Claude rounds are compared
  with Codex rounds on the same frozen oracle, not merged into one streak.
- Historical Codex request hashes are unchanged (defaults serialize identically).
- Model access is unverified until a live round; usage is reported from the
  CLI stream, monetary cost under a subscription is not.
