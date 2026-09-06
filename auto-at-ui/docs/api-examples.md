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

## Vision advisory-session progress

An authenticated project reader can retrieve safe, session-scoped progress:

    curl -b cookies.txt http://127.0.0.1:7000/api/v1/vision/explorations/SESSION_ID/activities
    curl -N -b cookies.txt -H "Last-Event-ID: ACTIVITY_EVENT_ID" http://127.0.0.1:7000/api/v1/vision/explorations/SESSION_ID/activities/stream

The SSE stream emits named activity messages, returns history before new events,
and does not replay the supplied valid Last-Event-ID. Its records contain safe
summaries and allow-listed metadata only; they never include screenshots, intent,
typed text, prompts, provider output, credentials, or a verdict.

## Vision visual replay

Project readers can list metadata and retrieve one verified frame through the
control plane; neither response exposes a RustFS URL. A tenant administrator
can explicitly remove a frame or full replay with the session CSRF token.

    curl -b cookies.txt http://127.0.0.1:7000/api/v1/vision/explorations/SESSION_ID/replay-frames
    curl -b cookies.txt -H "Accept: image/png" http://127.0.0.1:7000/api/v1/vision/explorations/SESSION_ID/replay-frames/FRAME_ID --output state.png
    curl -b cookies.txt -X DELETE -H "Content-Type: application/json" -H "X-CSRF-Token: CSRF_VALUE" -d '{"confirm":true}' http://127.0.0.1:7000/api/v1/vision/explorations/SESSION_ID/replay-frames/FRAME_ID

Do not copy the image into logs, tickets, or public storage. A missing, corrupt,
or deleted frame returns a non-enumerating error and cannot affect a draft or
deterministic run verdict.
