---
name: auto-at-session-bootstrap
description: Bootstrap repository understanding for the Auto-AT / agent-automation-testing repo at D:\CV\auto-at. Use when a session starts in this repo, before answering architecture questions, before planning implementation, before editing code, or when the user asks Codex to understand or work on this codebase. Ensures Codex reads AGENTS.md and README.md, checks CodeGraph availability, checks GitNexus status, uses GitNexus before broad grep/file reading, and reports the bootstrap evidence.
---

# Auto-AT Session Bootstrap

## Required workflow

When working in `D:\CV\auto-at` or the `agent-automation-testing` GitNexus repo:

1. Read `AGENTS.md`.
2. Read `README.md`.
3. Check whether `.codegraph/` exists at repo root.
   - If present, use CodeGraph before grep/find or manual file reads for code discovery.
   - If absent, state that CodeGraph does not apply.
4. Check GitNexus repo status for `agent-automation-testing`.
   - Use `mcp__gitnexus__list_repos` or the available GitNexus context resource.
   - If GitNexus reports stale index, run `npx.cmd gitnexus analyze`.
   - If analysis fails because it must write outside the workspace, request escalation.
   - If GitNexus remains stale/degraded after best effort, say so and continue with docs + targeted reads.
5. Use GitNexus before broad grep/file reading when exploring code:
   - `query` for concepts and flows.
   - `context` for specific symbols.
   - `impact` before editing functions/classes/methods.
   - `detect_changes` before any commit.
6. Read relevant docs under `docs/` only after README/GitNexus point to them.
7. Before implementing or changing code, give a short bootstrap evidence note:
   - AGENTS.md read: yes/no
   - README.md read: yes/no
   - CodeGraph status
   - GitNexus status
   - Key files/docs selected

## Reporting style

Keep the bootstrap note short. Do not dump file contents. Report stale/degraded index state clearly.

Example:

```text
Bootstrap:
- AGENTS.md read
- README.md read
- CodeGraph: absent
- GitNexus: agent-automation-testing checked; index current/degraded/stale
- Scope: backend DAG runner + pipeline API
```

## Guardrails

- Do not edit any symbol until GitNexus impact analysis has been attempted.
- If GitNexus returns HIGH or CRITICAL risk, warn before editing.
- If instructions conflict, follow explicit user instructions first, then AGENTS.md, then this skill.
