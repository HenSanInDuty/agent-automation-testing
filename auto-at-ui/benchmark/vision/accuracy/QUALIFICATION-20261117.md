# Vision accuracy qualification — 2026-11-17

Status: **in progress; not qualified**. Canonical progress is recorded in
`plan/09112026103202-vision-accuracy-loop/README.md`.

Candidate `84354e173484092123a2728e3df4933b4cbbc77c9d8ea99dffbb4a69b1dd3eb3`
passed phase 04 in iteration `fd3ddda4-ca69-4abb-818b-a8ac1ad594d8`:
verified coverage 46/47 (97.8723%), interaction accuracy 46/48 (95.8333%),
detection precision 46/48 and recall 46/47, complete inventory, zero unsafe or
unsettled operations. This single passing development run does not establish
repeatability. Three fresh consecutive qualification runs are still required.

The frozen oracle, model `codex_cli/gpt-6-luna`, v11 prompt, browser and policy
are unchanged. See `qualification-candidate-20261117.json`, the iteration
manifest/provenance, and its 46 content-addressed outcome reviews.

## Final-source checks

- Worker operations/visual-buttons matrix: 102 passed (6.2m).
- Worker typecheck, Ruff, generated worker contract and scoped diff checks: passed.
- Full isolated Python suite: running; results pending.
- Fresh live qualification sequence: not started.

## Scope and retained limitations

The benchmark covers the frozen desktop homepage annotations at 1280×720.
It does not certify business outcomes, other websites or population-level
reliability. Navigation credit verifies declared destinations or independently
reviewed redirects; it does not certify login, payment, download execution or
media playback. YouTube after-images show loading shells with the exact declared
playlist URL; only destination navigation is credited.

The development run's unmatched video-copy click and rejected video click remain
in the interaction denominator without credit. The frozen video target mct-47
remains unverified. Runtime `unavailable/unsafe_replay` is unchanged: the worker
refused restoration to a superseded carousel checkpoint. The benchmark does not
override that conclusion. Four unavailable frames belong to rejected operations;
all 292 retained frames were verified, including every frame used for credit.

Earlier failed runs remain in `runs/` and are not removed or relabeled.
