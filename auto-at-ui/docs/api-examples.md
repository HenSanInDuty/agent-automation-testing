# Dashboard session API examples

The dashboard uses an HttpOnly session cookie and CSRF token. Do not send
`X-Tenant-Id`, `X-Actor-Id`, or `X-Actor-Roles` from browser clients. Those
headers exist only for local compatibility tooling and do not replace session
authorization.

Sign in and retain the cookies locally:

```bash
curl -c cookies.txt -X POST http://127.0.0.1:7000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"demo-tenant","email":"admin@example.test","password":"TEMPORARY_PASSWORD"}'
```

Copy the `auto_at_csrf` value from `cookies.txt` when sending a state-changing
request. The dashboard API client does this automatically.

```bash
curl -b cookies.txt http://127.0.0.1:7000/api/v1/projects

curl -b cookies.txt -X POST http://127.0.0.1:7000/api/v1/runs \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "X-CSRF-Token: CSRF_VALUE" \
  -d '{"project_id":"PROJECT_ID","test_case_id":"TEST_ID","target_type":"web_ui","runner_config":{},"artifact_policy":{"trace_on_failure":true,"video_on_failure":true,"screenshot_on_failure":true,"retain_days":30}}'
```

The server authorizes every project, run, artifact, activity, generation, and
review response. Artifact downloads use the run-scoped download route; never
render a storage URI as a browser link.
