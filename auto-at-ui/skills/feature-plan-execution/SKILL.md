---
name: feature-plan-execution
description: Implement an approved feature plan phase by phase and keep its canonical README progress record current. Use when a user asks to execute, implement, continue, or complete a plan created under ./plan/, including ongoing work that must not pause except at a phase boundary or for a material question.
---

# Feature Plan Execution

Implement the plan as the source of scope and keep it truthful. Do not silently expand, reinterpret, or mark work complete without evidence.

## 1. Load and validate the plan

1. Locate the requested plan directory under `./plan/`. If none is named and multiple plans exist, ask the user which one to execute. If exactly one exists, use it.
2. Read its `README.md` and the current phase file completely. Read prior completed phase files when their outputs are dependencies.
3. Read `AGENTS.md`, `README.md`, relevant ADRs, and every source/test file named by the phase before editing. Run `git status --short` and preserve unrelated changes.
4. Reconcile the plan against the current checkout. If source, contracts, requirements, or prerequisites materially differ, update the plan documents with a clearly marked revision only after confirming the changed scope with the user when required.

## 2. Choose the next work unit

Work on the first phase whose status is `not started` or `in progress`, respecting dependencies. Mark it `in progress` in the plan README before implementation, with the start timestamp and a brief scope note.

If a phase is already in progress, resume it from the recorded remaining work. Do not skip a phase or perform unrelated cleanup.

## 3. Execute continuously within a phase

Continue working through the active phase without pausing, requesting a status check, or yielding the task merely because an intermediate step is difficult. Investigate failures, inspect source, implement scoped fixes, and run the smallest relevant checks as part of the phase.

Only stop for user input when one of these conditions is true:

- the phase is complete and validated;
- a material missing decision changes behavior, acceptance criteria, API/data shape, scope, or protected architectural choice;
- required access, credentials, or external state cannot be obtained through authorized means;
- an unexpected destructive, production-impacting, cost-incurring, or security-sensitive action needs explicit approval.

When blocked by a question, update the README with the exact blocker, decision needed, affected phase, and safe work already completed, then ask one concise question. Do not begin a later phase while it remains unresolved.

## 4. Keep the canonical README detailed and current

Immediately after a phase passes its acceptance criteria:

1. Update `README.md` in the plan directory and the corresponding phase file.
2. Set the phase status to `completed`, record completion timestamp, implementation summary, exact changed paths, validation commands/results, deviations from the original plan, and follow-up risks or deferred items.
3. Update the phase table, overall progress summary, dependencies unlocked, and next phase.
4. Never claim a test passed unless it was actually run and passed; record skipped validations and why.

If a phase fails validation but remains active, leave it `in progress` and record the failed command/result and remediation underway. Do not mark it complete.

## 5. Phase handoff and completion

After updating the README for a completed phase, either immediately begin the next unblocked phase or, if the user requested only one phase, stop and report the completed phase and its evidence. Continue automatically through all phases only when the user asked to execute/complete the full plan.

At final completion, update the README's overall status to `completed`, run the plan's final validation, and report changed files, validations, deviations, and any deliberately deferred follow-up. Never modify execution verdicts or test suites outside the plan's explicit approval boundary.
