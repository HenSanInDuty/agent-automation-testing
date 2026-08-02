---
name: feature-planning
description: Scout a repository and produce a detailed, implementation-ready, phased feature plan. Use when a user asks to plan, scope, break down, or prepare a feature before implementation, especially when the plan must be saved under ./plan/ and include source-grounded file and test changes.
---

# Feature Planning

Create a decision-ready plan, not implementation. Do not modify production code, configuration, migrations, or tests while using this skill.

## 1. Establish context before planning

1. Read the repository `AGENTS.md`, `README.md`, applicable architecture records/ADRs, and project/tooling files relevant to the requested feature.
2. Run `git status --short` first and preserve unrelated user changes.
3. Scout the source before proposing a solution. Use `rg --files`, `rg`, and targeted file reads to identify the current behavior, ownership layer, contracts, existing tests, adjacent features, and extension points.
4. State concise evidence from the scout: relevant paths, current behavior, constraints, and missing information.

For changes involving execution contracts, agents/LLMs, infrastructure, or a new runner, explicitly check the repository's required pre-flight concerns. Never decide a provider, model, cloud, authentication choice, retention policy, or other protected architectural choice without user direction.

## 2. Resolve material ambiguity immediately

Ask focused questions **before creating the plan** whenever an answer materially changes scope, behavior, acceptance criteria, data/API shape, rollout, or a protected architecture choice. Ask only questions that cannot be safely answered from the repository and request.

Do not ask for minor implementation preferences when the existing codebase establishes a clear convention. If no material ambiguity remains, state the assumptions that will govern the plan and continue.

## 3. Create the plan artifact

Create exactly one directory with this form:

```text
./plan/<ddmmyyyyHHMMSS><general-plan-name>/
```

- Generate the timestamp at creation time in local time, zero-padded; for example, `02082026153045`.
- Normalize `<general-plan-name>` to a short kebab-case name without brackets, spaces, or path separators; include a separating hyphen after the timestamp, for example `02082026153045-governed-draft-review`.
- If a collision occurs, generate a fresh timestamp; do not overwrite an existing plan.

Create these files:

```text
README.md
phase-01-<short-name>.md
phase-02-<short-name>.md
...
```

`README.md` is the canonical overview and progress view. Include:

- feature goal and measurable acceptance criteria;
- request, confirmed decisions, explicit assumptions, and unresolved questions;
- source-scout findings with file paths and concise evidence;
- architecture/contract/security or operational constraints that apply;
- an ordered phase table: number, objective, status (`not started` initially), dependencies, and validation;
- risks, rollout/migration considerations, and out-of-scope work;
- a link to every phase file.

Each phase file must be independently actionable. Include objective, scope, prerequisites, exact source paths to add/change, detailed behavior and data-flow steps, contract/API/schema changes, tests and validation commands, acceptance criteria, risks, and explicit non-goals. Sequence phases so each can be completed and verified independently.

Use repository-relative paths. Ground every proposed change in source evidence; distinguish confirmed facts from proposed design.

## 4. Finish

Review the complete plan for missing dependencies, test coverage, operational impact, and approval boundaries. Report the plan directory, major decisions, assumptions, and remaining questions. Do not start implementation; direct the user to `$feature-plan-execution` when they want a phase implemented.
