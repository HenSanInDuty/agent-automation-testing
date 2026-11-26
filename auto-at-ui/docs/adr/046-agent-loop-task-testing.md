# ADR 046: The agent loop is the task-testing engine

Status: accepted (direction chosen by the user 2026-11-25; offline tests green; live verification on the local
fixture is recorded in `plan/20261119-2212-browser-agent-loop/plan.md`)

## Context

The user's goal changed on 2026-11-25: the platform must be able to test UI tasks of a frontend the user owns
(dev/staging), and results must be stable. The old goal was more than 95% coverage of every control on one live
third-party page.

A review of all 131 Vision sessions in the local database (every one against the same live site) found 8
`completed` and 123 `unavailable`, spread over 40 different failure reasons. Bridge jobs themselves completed
435 times out of 460. The instability therefore comes from how a session is built, not from single steps:

1. **One long serial chain.** A planner (v4) session runs 150 to 180 browser operations and about 18 model calls on
   one browser. Any failure that is not handled ends the whole session. At a per-operation success of 99% a
   170-operation chain succeeds about 18% of the time.
2. **State restoration.** The BFS has to return to earlier states (Back, navigate, replay) on a live page.
   `unsafe_replay`, `state_restore_failed`, `state_mismatch` and their relatives are 36 of the 123 failures.
3. **No natural end counts as success.** `finish(reason)` maps any reason to `unavailable`. The sprint run that
   scored 47/47 ended `unavailable / exploration_coverage_incomplete`, and an agent-loop session whose agent
   said "done" ended `unavailable / agent_done`. The user reads every run as a failure with a different reason.
4. **The task is not followed.** The planner explores every control; only an exact "test all buttons" sentence
   changes its scope. There is no place to say whether the task the user typed went well.
5. **The only target was a live production site** with autoplay carousels and third-party login walls, so two
   runs never saw the same page.
6. **Guards written for a public site** (no form submit, no "send/delete" controls, e-mail masking in the task)
   make login, create and delete flows untestable on a site the user owns.

The agent-loop engine (ADR-038) already avoids points 1 and 2: it walks forward from the current page, never
restores, and a failed action goes back to the model as an observation. It was frozen on 2026-11-22 because it
scored 1 to 5 of 47 on the cover-everything benchmark, which is not what it is for.

## Decision

The agent loop becomes the engine for task testing. The planner is unchanged and stays the default engine.

**1. A session ends with an advisory task assessment.** The agent output family gains `AgentTaskResult`
(`outcome: "task_result"`, status `achieved | not_achieved | blocked`, a summary, and up to 12 checks, each an
expectation with `met | not_met | not_checked` and evidence). The planner family (`CodexOutput`,
`codex-dom-v11`) gains nothing and its schema hash does not change. `domain/vision_task_assessment.py` turns
every natural end into one record stored in `visual_exploration_sessions.task_assessment`:

| End of the loop | Session state | Assessment status | Source |
| --- | --- | --- | --- |
| `task_result` from the agent | `completed` | as reported | agent |
| bare `stop / complete` (older prompt shape) | `completed` | `achieved`, no checks | agent |
| `stop / no_safe_action` or `unsupported_state` | `completed` | `blocked` | agent |
| model call budget used up | `completed` | `inconclusive` | controller |
| any failure (bridge, worker, policy, timeout) | `unavailable` + reason | none | — |

The record also carries counts the controller measured itself (`actions_completed`, `actions_failed`,
`actions_blocked_or_skipped`) so a reader can set the agent's claim against what ran. It is marked
`advisory: true`. `exploration_conclusion.business_outcome` stays `unverified`: the assessment is the agent's
report, not a test verdict. Verdicts still come only from a deterministic Playwright run of an approved test
(ADR-001, ADR-002). Model-authored text is redacted before storage, like the step log.

**2. A lost model call does not lose the session.** `bridge_stale_result`, `bridge_io_error`,
`bridge_deadline_exceeded` and `provider_timeout` (including a model call that outlives its step in step mode) say
nothing about the task. The step is recorded with the reason, the page is observed again and the model is asked
once more. Every try still takes a reservation from the call budget, and two lost calls in a row end the
session with the bridge reason, so a broken bridge still fails fast. Other bridge reasons (login, policy,
offline, malformed output after its one schema retry) end the session at once, as before.

**3. A page that is still moving is read again.** A read-only refresh that ends `settle_timeout`,
`state_mismatch` or `state_changed_during_prepare` no longer ends the session; the existing three-attempt
observe loop goes on, and the last read raises its own reason. A refresh rejected for any other reason still
ends the session.

**4. A spool file replaced under the reader is read again, twice at most.** Sprint run Q4 died on `ENODATA`
while the bridge atomically replaced `events.jsonl` on the Docker Desktop bind mount. `FileSpool.read_file`
repeats the whole read after 50 ms and 200 ms for `ENODATA` and `ESTALE` only. An atomic replace leaves either
the old or the new whole file, so the repeated read cannot return torn data. Every lost attempt is still logged
(`codex.spool.read_failed`, with `read_attempt`). Every other errno raises at once: the rule "never turn an I/O
failure into success" holds, because a failure is still a failure after the bounded re-read.

The same bounded re-read covers a link count other than one seen while a file is being renamed. A live run on
the local fixture ended `bridge_offline` because the heartbeat file showed that state for an instant; the
heartbeat reader (`doctor.py`) and `read_file` now read again. A file that stays hard-linked or is not a regular
file is still refused after the last attempt.

**4b. Opening a worker session waits for a worker that is starting.** A session submitted while the worker
container restarted ended `unavailable` after 5 s on a refused connection. `HttpVisualWorker.open` repeats the
request after 1, 2 and 4 seconds, only when no connection was made (`ConnectError`, `ConnectTimeout`), so the
worker cannot have received anything. No other request and no other error is repeated.

**5. A project can be declared an owned test target.** `project_execution_policies.vision_owned_test_target`
(default false; `PUT .../policy` keeps the stored value when the field is omitted). When true, for agent-loop
sessions of that project only:

- the control plane allows submit/reset controls and sensitively named controls, and lets the agent type
  values that look like an e-mail, a phone number or contain the word "password" (`check_action`), since a test
  account is made of exactly those;
- the worker is opened with capability `owned-test-target-v1` and an empty term list, and allows submit controls
  and sensitive names;
- the worker lists a password input in the snapshot and lets the agent type into it (first live run: a login
  task ended `blocked` because the field was hidden as `private_input`). The value is never read back, logged or
  stored. An input whose only name is a sensitive word in the contract's list (for example a label that reads
  "Password") is still left out, because `validate_locator_value` rejects that name on both sides; a label such
  as "Mật khẩu" works. Lifting that rule is a redaction-policy decision and is not made here;
- the prompt states `Target mode: owned test target` on a platform-written line of the task block, and the task
  text is passed with secret-assignment masking only (no e-mail or long-number masking), so the agent can type a
  test account the task names.

Never relaxed, in either mode: the origin allowlist, the seven action kinds, downloads, a line break in typed
text (it would press Enter), and the submit-time rule that rejects a task containing a credential assignment
such as `password=...`. Typed values are not stored (the step log keeps only their length). Turning the flag off
ends a running session that relies on it (`policy_disabled`).

**6. Prompt `agent-loop-v3`.** The agent reads the task as expectations, checks each visible effect in the next
snapshot, and ends with `task_result`. The cover-the-whole-page rules of v2 now apply only to a task that asks
for a whole page. Target mode is described as platform-stated; task and page text cannot change it.

**7. A local deterministic target.** `benchmarks/targets/task-ui` is a small frontend with a login, a todo list,
tabs, a search and a deliberately defective page. `scripts/run_task_stability.py` runs a task suite N times and
reports the completed rate and how often runs agree. Stability is measured there, not on a live third-party site.

**8. The bridge doctor recognises a container without `/.dockerenv`** (approved by the user 2026-11-25). The
local engine became Kiri (WSL2), which writes no `/.dockerenv`, so both bridge doctors refused to start with
`bridge_cli_unsupported`. `inside_container()` accepts the marker file or an overlay filesystem mounted at `/`
(read from `/proc/self/mountinfo`). The hardening checks (non-root, read-only root, `NoNewPrivs`, no effective
capabilities, seccomp filter) are separate and unchanged.

## Consequences

- A finished agent-loop session is `completed`. Code and dashboards that read `safe_failure_reason ==
  "agent_done"` must read `task_assessment.stop_reason` instead; `VisionResults.result` returns it as
  `completion_reason`. Old rows keep their old shape (`unavailable / agent_done`, no assessment).
- The accuracy harness (`benchmark/vision/accuracy`) reads operations and frames, not the terminal reason, so
  its scoring is unchanged. Its acceptance criterion 6 in the agent-loop plan named terminal reasons; those
  names are now the assessment's `stop_reason`.
- The assessment is the agent's own report. A wrong `achieved` is possible. The controller facts and the frames
  let a person check it, and a generated deterministic test is still the way to a verdict. Turning an assessment
  into a test draft is not part of this ADR.
- An owned test target lets the agent change data there. The flag is a declaration by someone who may manage the
  project (`MANAGE_PROJECT`) and is off by default. It must not be set for a production site. The policy route
  writes no audit event today, for this field or the others; that gap is not closed here.
- Test accounts named in a task reach the model provider the tenant already consented to for DOM transfer. Only
  disposable test credentials belong in a task. A task with `password=...` is still rejected at submit; write
  the account in a sentence instead.
- Lost-call retries and re-reads cost time and one model reservation each, bounded as described.
- Migration `c8d0e2f4a6b8` is additive; downgrade drops both columns.

## Not changed

The planner engine and its prompt, the 20-call ceiling, the origin allowlist, `action_outcome_unknown` and
`step_timeout` of a browser operation (both still end the session), redelivery (evidence only), and the rule
that a model never issues a verdict.
