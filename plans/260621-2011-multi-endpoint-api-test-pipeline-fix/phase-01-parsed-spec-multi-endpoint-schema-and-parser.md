# Phase 01 — Multi-endpoint ParsedSpec schema + parser

## Context Links
- `backend/app/tools/md_api_spec_validator.py` (schema + parser — owner of this phase)
- Symptom doc: `TodoCode/api_documentation-pipeline.md` (9 endpoints)
- Inter-node contract: `dag_pipeline_runner.py:46` `_NON_PROPAGATING_KEYS` (md_spec_parsed propagates)

## Overview
- **Priority:** P1
- **Status:** pending
- **Description:** Turn `ParsedSpec` from single-endpoint into multi-endpoint, and stop the parser
  dropping every endpoint after the first. Keep a backward-compat surface so existing callers/tests
  that read `.endpoint`/`.request`/`.responses` keep working until they are migrated (phases 02-04).

## Key Insights
- `_extract_sections` (`md_api_spec_validator.py:342-346`) deliberately keeps only the FIRST body
  per canonical section. With 9 `### Endpoint` blocks under repeated `## API: …` headings, only the
  first `GET /api/tasks` survives.
- `ParsedSpec` (`:91-97`) is single-endpoint: `endpoint`, `request`, `responses`, `response_body`.
  `headers` + `base_url` are spec-level (shared) — keep them at spec level.
- The MD contract groups each endpoint under a top-level `## API: <name>` (H2) with `### Endpoint`,
  `### Request`, `### Response` (H3) children. Section splitting must become **per-endpoint group**,
  not a flat first-wins map.
- Existing tests construct `ParsedSpec(endpoint=ParsedEndpoint(...), request=..., responses=[...])`
  and read `result.parsed.endpoint.method` (`test_md_api_spec_validator.py:25-35`,
  `test_adaptive_api_test_planner.py:38-55`, `test_senior_coverage_review_loop.py:65-69`).
  → **Backward-compat is mandatory** (KISS: do not rewrite all tests in this phase).

## Requirements
**Functional**
- Parse all endpoint groups in the document (9 for the sample).
- Each endpoint carries its own method/path/auth, request body, and responses.
- `base_url` and `headers` remain spec-level.
- Validation still raises `MDSpecValidationError` in strict mode when an endpoint is malformed
  (method/path/response missing). Per-endpoint validation must aggregate violations.

**Non-functional**
- File stays < 200 lines? Current file is 621 lines — already over. Do NOT inflate further than
  necessary; if the schema models + grouping logic push it materially larger, extract the Pydantic
  models into a sibling module `md_api_spec_models.py` and re-export them from
  `md_api_spec_validator.py` so import paths (`from app.tools.md_api_spec_validator import ParsedSpec`)
  stay stable. Decide during implementation; prefer extraction only if needed.
- Parser remains deterministic, no LLM, no I/O.

## Architecture

### New model shape (additive, backward-compatible)
```
class ParsedEndpointSpec(BaseModel):
    endpoint: ParsedEndpoint = Field(default_factory=ParsedEndpoint)
    request: ParsedRequest = Field(default_factory=ParsedRequest)
    responses: list[ParsedResponse] = Field(default_factory=list)
    response_body: str = ""

class ParsedSpec(BaseModel):
    base_url: str = ""
    endpoints: list[ParsedEndpointSpec] = Field(default_factory=list)
    headers: list[ParsedHeader] = Field(default_factory=list)

    # Backward-compat surface — first endpoint, never raises on empty.
    @property
    def endpoint(self) -> ParsedEndpoint: ...   # endpoints[0].endpoint or ParsedEndpoint()
    @property
    def request(self) -> ParsedRequest: ...
    @property
    def responses(self) -> list[ParsedResponse]: ...
    @property
    def response_body(self) -> str: ...
```
- **Why properties (not stored fields):** existing constructor calls pass `endpoint=`/`request=`/
  `responses=`. Provide a `model_validator(mode="before")` that, when legacy kwargs
  (`endpoint`/`request`/`responses`/`response_body`) are present and `endpoints` is absent, folds
  them into a single `ParsedEndpointSpec` and populates `endpoints`. This keeps every existing test
  constructing single-endpoint specs valid without edits.
- **Serialization contract:** `model_dump()` now emits `endpoints: [...]` plus `base_url`,
  `headers`. The legacy `endpoint`/`request`/`responses` are read-only properties → NOT serialized
  (pydantic v2 does not serialize plain `@property`). Downstream `ParsedSpec.model_validate(dict)`
  reads `endpoints`. Phases 02-04 migrate consumers to iterate `endpoints`; until then they use the
  compat properties, which still resolve from `endpoints[0]`.

### Parser change — `_extract_sections` → per-endpoint grouping
- Replace the flat first-wins `sections` dict with logic that:
  1. Walks H2/H3 headings in order.
  2. Treats each `## API: …` (or any H2 that is not itself an `endpoint`/`request`/`response`/`headers`
     alias) as the start of a new endpoint group. Spec-level `## Headers` stays spec-level.
  3. Within a group, collects the `endpoint`/`request`/`response` H3 bodies (first-wins WITHIN a group).
  4. Emits a list of `(endpoint_body, request_body, response_body)` groups.
- Keep `## Headers` extraction at spec scope (it is shared) — the sample has one spec-level
  `## Headers` table.
- Edge cases to handle:
  - Repeated `## API: Tasks` headings (sample uses the same name 4×) → each is its own group; do NOT
    dedupe by title.
  - A document where endpoint sections appear at H2 directly (no `## API:` wrapper) → fall back to
    grouping by each `### Endpoint` (or `## Endpoint`) occurrence.
  - Spec-level `## Headers` must not be swallowed into the first endpoint group.

### Validation loop
- `validate_md_api_spec` builds `parsed.base_url` + `parsed.headers` once (spec-level), then loops
  groups → builds one `ParsedEndpointSpec` per group, aggregating per-endpoint violations (prefix
  field codes with endpoint index where helpful, e.g. `endpoints[2].method`).
- `requires_body` is decided per endpoint method (GET/DELETE legitimately bodyless).
- Missing-section logic runs per group; an empty document (no endpoint group) keeps the existing
  `missing_sections=["endpoint", ...]` behaviour.

## Related Code Files
**Modify**
- `backend/app/tools/md_api_spec_validator.py` — add `ParsedEndpointSpec`, restructure `ParsedSpec`,
  add `model_validator` + compat properties, rewrite `_extract_sections` to per-group, restructure
  `validate_md_api_spec` to loop groups.

**Create (only if file size demands)**
- `backend/app/tools/md_api_spec_models.py` — Pydantic models, re-exported from the validator.

**Delete** — none.

## Implementation Steps
1. Add `ParsedEndpointSpec`; restructure `ParsedSpec` to `endpoints/base_url/headers` + compat
   properties + `model_validator(mode="before")` that folds legacy kwargs into `endpoints`.
2. Rewrite `_extract_sections` → `_extract_endpoint_groups(text, synonyms)` returning
   `(spec_headers_body, list_of_group_section_dicts)`. Preserve the H2/H3 detection and the
   `API: <name>` prefix stripping (`:332`).
3. Rewrite the body of `validate_md_api_spec`: parse base_url + headers once; loop groups building
   `ParsedEndpointSpec`; aggregate violations; assemble `ParsedSpec(endpoints=…, base_url=…, headers=…)`.
4. Keep `to_summary` working (it reads `result.*` flat fields — unaffected).
5. Run `python -m py_compile` + import smoke test (`python -c "from app.tools.md_api_spec_validator import ParsedSpec, ParsedEndpointSpec, validate_md_api_spec"`).

## Todo List
- [ ] Add `ParsedEndpointSpec` model
- [ ] Restructure `ParsedSpec` (endpoints list + spec-level headers/base_url)
- [ ] Add `model_validator(before)` folding legacy `endpoint/request/responses` kwargs
- [ ] Add compat `@property` for `endpoint`/`request`/`responses`/`response_body`
- [ ] Rewrite `_extract_sections` → per-endpoint grouping (`## API:` aware, headers spec-level)
- [ ] Restructure `validate_md_api_spec` to loop groups + aggregate violations
- [ ] py_compile + import smoke test
- [ ] If file materially > 200 lines beyond current, extract models to `md_api_spec_models.py` and re-export

## Success Criteria
- `validate_md_api_spec(open(TodoCode/api_documentation-pipeline.md).read()).parsed.endpoints` has length 9.
- `parsed.base_url == "http://localhost:8080"`, `parsed.headers` has `Content-Type`.
- Legacy access `parsed.endpoint.method == "GET"`, `parsed.endpoint.path == "/api/tasks"` (first endpoint).
- `ParsedSpec(endpoint=ParsedEndpoint(method="POST", path="/users"), responses=[ParsedResponse(status_code=200)])`
  still constructs and `.endpoints` has length 1 (validator-fold works).
- Existing `test_md_api_spec_validator.py` assertions on `.endpoint`/`.responses`/`.request` pass unchanged.

## Risk Assessment
| Risk | L×I | Mitigation |
|------|-----|-----------|
| `model_validator` fold breaks pydantic v2 serialization round-trip (`model_dump`→`model_validate`) | M×H | Round-trip test: dump multi-endpoint spec, re-validate, assert equality. The fold only triggers when `endpoints` absent AND legacy keys present, so a re-loaded dump (which has `endpoints`) is untouched. |
| `@property` named same as a former field shadows nothing but a stored value is expected elsewhere | M×M | grep confirms all reads are attribute reads, satisfied by property. Writers (`parsed.endpoint = …`) exist only INSIDE the validator (`:161,194,211`) and are being rewritten in this phase. |
| Headers section mis-grouped into an endpoint | M×H | Treat `headers` alias H2 as spec-level explicitly; unit test on the sample asserts 1 spec-level header table + 9 endpoints. |
| File exceeds 200-line guideline | H×L | Optional model extraction to `md_api_spec_models.py`; not a correctness risk. |

## Security Considerations
- Header redaction / `_safe_header_schema` (`:477`) unchanged — secret headers still mapped to
  `runtime credential`. No new sink for secrets introduced.

## Next Steps
- Unblocks phases 02 (generator/obligations), 03 (complexity/prompts/crew preview), 04 (runner).
- Phases 02-04 migrate their consumers from compat properties to `for ep in parsed.endpoints:` loops.
