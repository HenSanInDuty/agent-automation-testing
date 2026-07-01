# Phase 04 — Runner Base URL fix (parsed source + regex)

## Context Links
- `backend/app/tools/api_test_runner.py` (`_RE_BASE_URL:35`, `execute_test_cases`)
- `backend/app/crews/api_test_runner_crew.py` (`run` → `execute_test_cases:82`)
- `dag_pipeline_runner.py:46` `_NON_PROPAGATING_KEYS` — `md_spec_parsed` carries forward to runner
- Depends on Phase 01 (so `md_spec_parsed.base_url` shape is stable) — but the regex part is independent.

## Overview
- **Priority:** P1
- **Status:** pending
- **Description:** The runner skips every executable case because its Base URL regex does not accept
  the bullet form `- Base URL: …`. Fix by (b) consuming the already-correctly-parsed
  `md_spec_parsed.base_url` as `base_url_override` — the source of truth — and (a) hardening the
  runner regex with `[-*]?` as defense-in-depth.

## Key Insights
- Document line 3 is `- Base URL: http://localhost:8080` (bullet). Validator regex
  (`md_api_spec_validator.py:50`) already accepts `[-*]?` and parses it correctly into
  `parsed.base_url`. The runner's `_RE_BASE_URL` (`api_test_runner.py:35`,
  `r"(?im)^\s*Base\s*URL\s*[:=]\s*(\S+)"`) lacks `[-*]?` → no match → `base_url=""`.
- `execute_test_cases` (`:59`) picks `base_url_override or _extract_base_url(document_content)`.
  When base_url is empty, `:87` forces every case to SKIPPED with reason "No Base URL configured".
  This is exactly the "both SKIPPED" symptom.
- `ApiTestRunnerCrew.run` (`api_test_runner_crew.py:82-85`) calls `execute_test_cases` with ONLY
  `test_cases` + `document_content` — it never passes `base_url_override`, even though
  `md_spec_parsed` is present in `input_data` (carried forward through the DAG — verified:
  `md_spec_parsed` not in `_NON_PROPAGATING_KEYS`).
- **Primary fix (b):** in the crew, read `input_data["md_spec_parsed"]["base_url"]` and pass it as
  `base_url_override`. This decouples execution from the weak document-scraping regex entirely.
- **Defense-in-depth (a):** add `[-*]?` to `_RE_BASE_URL` so the document fallback also works if
  `md_spec_parsed` is ever absent.

## Requirements
**Functional**
- When `md_spec_parsed.base_url` is a valid URL, the runner uses it and executable cases run
  (not skipped for "No Base URL").
- When `md_spec_parsed` is missing but the doc has a bullet `- Base URL:` line, the hardened regex
  still recovers it.
- No behaviour change when base_url genuinely absent (cases still skip with the existing reason).

**Non-functional**
- Both files well under 200 lines; keep changes minimal (KISS).

## Architecture

### Data flow
```
md_api_spec_verifier → md_spec_parsed{base_url, endpoints, headers}  (carried forward)
   ↓ (DAG carry-forward through testcase/classifier nodes)
api_test_runner node → ApiTestRunnerCrew.run(input_data)
   base_url_override = (input_data.get("md_spec_parsed") or {}).get("base_url") or None
   execute_test_cases(test_cases, document_content, base_url_override=base_url_override)
```
- `execute_test_cases` already supports `base_url_override` (`:41,59`) — no signature change.
- Precedence inside `execute_test_cases` is `base_url_override or _extract_base_url(doc)` — correct:
  parsed value wins, doc scrape is fallback.

### Regex change
- `_RE_BASE_URL = re.compile(r"(?im)^\s*[-*]?\s*Base\s*URL\s*[:=]\s*(\S+)")`
  (mirror the validator: also tolerate `Base[\s_-]*URL` if we want full parity — keep minimal:
  add `[-*]?\s*` after `^\s*`). Align with validator's pattern to avoid divergence.

## Related Code Files
**Modify**
- `backend/app/crews/api_test_runner_crew.py` — derive `base_url_override` from `md_spec_parsed`,
  pass to `execute_test_cases`; add a log line stating the resolved base_url source.
- `backend/app/tools/api_test_runner.py` — add `[-*]?` to `_RE_BASE_URL` (defense-in-depth).

**Delete** — none.

## Implementation Steps
1. In `ApiTestRunnerCrew.run`, after reading `test_cases`/`document_content`, add
   `parsed = input_data.get("md_spec_parsed") or {}` and
   `base_url_override = (parsed.get("base_url") or None) if isinstance(parsed, dict) else None`.
2. Pass `base_url_override=base_url_override` to `execute_test_cases`.
3. Emit a log: `Base URL resolved from {'parsed spec' if base_url_override else 'document'}: {…}`.
4. Update `_RE_BASE_URL` in `api_test_runner.py` to include `[-*]?` (mirror validator).
5. py_compile both; unit test both paths.

## Todo List
- [ ] Crew reads `md_spec_parsed.base_url` → `base_url_override`
- [ ] Pass `base_url_override` into `execute_test_cases`
- [ ] Log resolved base_url + source
- [ ] Add `[-*]?` to `_RE_BASE_URL` (defense-in-depth)
- [ ] py_compile + unit tests for both paths

## Success Criteria
- `execute_test_cases([executable_case], document_content="- Base URL: http://x\n")` returns the
  case NOT skipped for "No Base URL" (regex fix).
- `ApiTestRunnerCrew.run({"test_cases":[exec_case], "md_spec_parsed":{"base_url":"http://x"}, "document_content":""})`
  resolves base_url from parsed spec and does not skip for missing base URL.
- With no base_url anywhere, cases still skip with the existing "No Base URL configured" reason.

## Risk Assessment
| Risk | L×I | Mitigation |
|------|-----|-----------|
| `md_spec_parsed` shape changed in Phase 01 breaks `.get("base_url")` | L×H | `base_url` stays a top-level spec field in the new shape (Phase 01 design); test asserts it. |
| Live HTTP calls during tests (runner hits network) | M×M | Tests assert SKIP/non-skip classification only, or monkeypatch `run_api_request`; do not require a live server. |
| Regex over-matches a line like `Base URL note: see below` | L×L | `(\S+)` captures first token; same risk pre-existing; validator parity keeps behaviour consistent. |
| Carry-forward could drop `md_spec_parsed` if a future node overwrites it | L×M | Regex fallback (a) covers this; note the dependency in docs. |

## Security Considerations
- No credential handling here. base_url is non-secret. Headers/secrets handled upstream.

## Next Steps
- Independent of Phase 02/03 (distinct files); run in parallel after Phase 01.
- Phase 05 adds the bullet-base-url no-skip test.
