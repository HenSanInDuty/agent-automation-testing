# Claude local bridge (`claude -p`)

Claude runs as the Vision provider `claude_cli` / `claude-opus-5-5` through the
same DOM-first local bridge protocol as Codex. No Anthropic API key is used: the
bridge container runs `claude -p` with the existing Claude Code login.
Decision record: [ADR-037](adr/037-claude-cli-bridge-engine.md).

## What is identical to Codex

- Spool, job/claim/response protocol, deadlines, fencing, consent snapshot and
  hashes; DOM-first observation; optional screenshot stage with separate consent.
- Task prompt `codex-dom-v11` and the response JSON schema (byte-identical), the
  local validator, target preflight, guards, oracle and scoring.

## What differs

- Engine: `claude -p` (Claude Code 2.1.328), `--effort low`, fixed argv
  (`claude_process.py`). Built-in tools, MCP servers, settings files, slash
  commands and session persistence are all disabled; the only tool is the
  `StructuredOutput` tool created by `--json-schema`. Any other tool, MCP server
  or model in the event stream fails the job (`bridge_tool_rejected` /
  `bridge_model_unavailable`).
- System prompt: `agents/prompts/claude_bridge.py` replaces Claude Code's coding
  agent prompt. The task prompt is unchanged.
- Draft generation stays on Codex; the Claude engine only answers Vision jobs.
- One bridge runs one engine. `codex-bridge` and `claude-bridge` share the bridge
  ID and spool, so run exactly one of them. Readiness carries the provider, and a
  bridge answers another provider's job with `bridge_model_unavailable`.

## Credentials

The container receives only an OAuth **access** token file, never the refresh
token, so it cannot rotate or log out the host login:

```powershell
uv run python scripts/export_claude_bridge_token.py $HOME/.auto-at/claude-bridge-secrets
```

The access token expires after a few hours (the script prints the remaining
time); rerun it, or put a long-lived token from `claude setup-token` in the same
file. An expired token surfaces as `bridge_login_required`. Usage counts against
the Claude subscription of that login.

## Start / switch

```powershell
$env:CLAUDE_BRIDGE_TOKEN_DIR = "$HOME/.auto-at/claude-bridge-secrets"
docker compose -f docker-compose.yml -f docker-compose.codex.yml --profile codex stop codex-bridge
docker compose -f docker-compose.yml -f docker-compose.codex.yml --profile claude build claude-bridge
docker compose -f docker-compose.yml -f docker-compose.codex.yml --profile claude up -d claude-bridge
```

Then in **Vision settings** select **Claude (claude -p, local bridge)**, accept
page-element transfer to Anthropic (and optionally screenshots), enable and save.
Switching provider clears consent. Rollback: stop `claude-bridge`, start
`codex-bridge`, select Codex again.

## Validation

- `tests/test_claude_bridge.py`: contracts, policy, argv, event validation,
  engine/provider binding, heartbeat identity (offline, no model call).
- Host probe (2026-11-19): real `claude -p` with the production schema returned a
  schema-valid `CodexOutput` through `ClaudeEventReader`.
