"""Scoped read-only DOM transport through synthetic HTTP only."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from auto_at.contracts.vision_worker import VisualWorkerObserveDom, VisualWorkerOpen
from infrastructure.vision_worker import HttpVisualWorker, VisualWorkerUnavailable
from test_codex_bridge_contracts import observation


@pytest.mark.parametrize("change", [None, "tenant", "fence", "snapshot", "fingerprint",
                                  "sensitive", "binding", "count", "bytes", "extra", "type"])
def test_dom_transport_validates_scope_bounds_safe_text_and_binding(change):
    obs = observation()
    req = VisualWorkerObserveDom(
        tenant_id=obs.tenant_id, project_id=obs.project_id, session_id=obs.session_id,
        fencing_token=obs.fencing_token, snapshot_id=obs.snapshot_id,
        expected_state_fingerprint=obs.state_fingerprint,
    )
    data = {key: value for key, value in req.model_dump(mode="json").items()
            if key in {
                "contract_version", "tenant_id", "project_id", "session_id", "fencing_token",
            }}
    data.update(capability="dom-observation-v1", data={"observation": obs.model_dump(mode="json"),
        "bindings": [{"element_id": obs.elements[0].element_id,
                      "descriptor": {"strategy": "role", "role": "button", "value": "Continue"},
                      "bounds": {"x": 0, "y": 0, "width": 0.1, "height": 0.1}}]})
    if change == "tenant":
        data["tenant_id"] = "wrong"
    elif change == "fence":
        data["fencing_token"] = 2
    elif change == "snapshot":
        data["data"]["observation"]["snapshot_id"] = str(uuid4())
    elif change == "fingerprint":
        data["data"]["observation"]["state_fingerprint"] = "b" * 64
    elif change == "sensitive":
        data["data"]["observation"]["elements"][0]["name"] = "person@example.test"
    elif change == "binding":
        data["data"]["bindings"] = []
    elif change == "count":
        data["data"]["observation"]["elements"] *= 101
    elif change == "extra":
        data["data"]["observation"]["cookie"] = "synthetic-secret"

    def reply(request):
        assert request.url.path.endswith(f"/{req.session_id}/observations/dom")
        assert request.headers["x-auto-at-vision-worker-secret"] == "fixture"
        assert json.loads(request.content)["snapshot_id"] == str(req.snapshot_id)
        return httpx.Response(200, content=b" " * 256_001 if change == "bytes"
                              else json.dumps(data).encode(), headers={
                                  "content-type": "text/plain" if change == "type"
                                  else "application/json",
                              })

    async def read():
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
            return await HttpVisualWorker(client, "http://worker.test", "fixture").observe_dom(req)

    if change:
        with pytest.raises(VisualWorkerUnavailable):
            asyncio.run(read())
    else:
        assert asyncio.run(read()).data.observation == obs


@pytest.mark.parametrize("capabilities", [[], ["dom-observation-v1"]])
def test_codex_open_requires_explicit_dom_capability(capabilities):
    request = VisualWorkerOpen(
        tenant_id="fixture", project_id=uuid4(), session_id=uuid4(), fencing_token=1,
        target_url="https://fixture.test", allowed_origins=("https://fixture.test",),
        deadline=datetime.now(UTC) + timedelta(seconds=60), max_session_seconds=60,
        max_states=2, max_hops=1, max_screenshot_bytes=1024,
        required_capabilities=("dom-observation-v1",),
    )

    async def open_worker():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(
            200, json={"session_id": str(request.session_id), "contract_version": "v4",
                       "state_fingerprint": "a" * 64, "operation_budget": 11,
                       "capabilities": capabilities},
        ))) as client:
            return await HttpVisualWorker(client, "http://worker.test", "fixture").open(request)

    if capabilities:
        assert asyncio.run(open_worker()) == "a" * 64
    else:
        with pytest.raises(VisualWorkerUnavailable, match="capability"):
            asyncio.run(open_worker())
