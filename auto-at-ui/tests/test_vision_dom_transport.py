"""Scoped read-only DOM transport through synthetic HTTP only."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from auto_at.contracts.vision_worker import (
    VisualWorkerCheckTarget,
    VisualWorkerObserveDom,
    VisualWorkerOpen,
)
from domain.vision import VisionObservationUnavailable
from infrastructure.vision_worker import HttpVisualWorker, VisualWorkerUnavailable
from test_codex_bridge_contracts import observation


@pytest.mark.parametrize("change", [None, "session_id", "fencing_token", "snapshot_id",
                                   "element_id", "checkpoint_id", "context_matches",
                                   "same_document",
                                   "coerced_proof", "type"])
def test_readonly_target_check_rejects_wrong_identity_and_inconsistent_proof(change):
    request = VisualWorkerCheckTarget(tenant_id="fixture", project_id=uuid4(), session_id=uuid4(),
        fencing_token=1, snapshot_id=uuid4(), element_id="e_" + uuid4().hex, checkpoint_id=uuid4())
    payload = {**request.model_dump(mode="json"), "matches_current": True,
               "context_matches": True, "same_document": True}
    if change in {"session_id", "snapshot_id", "checkpoint_id"}:
        payload[change] = str(uuid4())
    elif change == "element_id":
        payload[change] = "e_" + uuid4().hex
    elif change == "fencing_token":
        payload[change] = 2
    elif change in {"context_matches", "same_document"}:
        payload[change] = False
    elif change == "coerced_proof":
        payload["matches_current"] = "true"

    async def check():
        def reply(incoming):
            assert incoming.url.path.endswith("/observations/target")
            assert incoming.headers["x-auto-at-vision-worker-secret"] == "fixture"
            return httpx.Response(200, content=json.dumps(payload).encode(),
                headers={"content-type": "text/plain" if change == "type"
                         else "application/json"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
            worker = HttpVisualWorker(client, "http://worker.test", "fixture")
            return await worker.check_target(request)
    if change is None:
        assert asyncio.run(check()).matches_current
    else:
        with pytest.raises(VisualWorkerUnavailable):
            asyncio.run(check())


@pytest.mark.parametrize("snapshot,targets,context,valid", [
    (True, False, True, True), (False, False, True, False),
    (True, True, True, False), (True, False, False, False),
])
def test_context_only_observation_cannot_be_confused_with_target_revalidation(
    snapshot, targets, context, valid,
):
    obs = observation()
    payload = dict(tenant_id=obs.tenant_id, project_id=obs.project_id,
                   session_id=obs.session_id, fencing_token=1, snapshot_id=uuid4(),
                   expected_state_fingerprint=obs.state_fingerprint,
                   revalidate_snapshot_id=uuid4() if snapshot else None,
                   revalidate_element_ids=(obs.elements[0].element_id,) if targets else (),
                   revalidate_context_only=context)
    if valid:
        assert VisualWorkerObserveDom(**payload).revalidate_context_only
    else:
        with pytest.raises(ValueError):
            VisualWorkerObserveDom(**payload)


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


@pytest.mark.parametrize("detail,expected", [
    ("state_mismatch", "state_mismatch"),
    ("state_changed_during_observation", "state_changed_during_observation"),
    ("stale_dom_context", "stale_dom_context"),
    ("stale_dom_target", "stale_dom_target"),
    ("private diagnostic token=secret", "dom_observation_unavailable"),
    ({"secret": "private"}, "dom_observation_unavailable"),
])
def test_dom_rejection_preserves_only_closed_safe_codes(detail, expected):
    obs = observation()
    req = VisualWorkerObserveDom(tenant_id=obs.tenant_id, project_id=obs.project_id,
        session_id=obs.session_id, fencing_token=obs.fencing_token,
        snapshot_id=obs.snapshot_id, expected_state_fingerprint=obs.state_fingerprint)

    async def read():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(422, json={"detail": detail}),
        )) as client:
            return await HttpVisualWorker(client, "http://worker.test", "fixture").observe_dom(req)
    with pytest.raises(VisionObservationUnavailable) as error:
        asyncio.run(read())
    assert str(error.value) == expected


@pytest.mark.parametrize("capabilities", [[], ["dom-observation-v1"],
                                        ["dom-observation-v1", "viewport-context-v1"],
                                        ["dom-observation-v1", "viewport-context-v1",
                                         "target-preflight-v1"]])
@pytest.mark.parametrize("preflight", [False, True])
def test_codex_open_requires_dom_and_viewport_context_capabilities(capabilities, preflight):
    request = VisualWorkerOpen(
        tenant_id="fixture", project_id=uuid4(), session_id=uuid4(), fencing_token=1,
        target_url="https://fixture.test", allowed_origins=("https://fixture.test",),
        deadline=datetime.now(UTC) + timedelta(seconds=60), max_session_seconds=60,
        max_states=2, max_hops=1, max_screenshot_bytes=1024,
        required_capabilities=("dom-observation-v1", "viewport-context-v1")
        + (("target-preflight-v1",) if preflight else ()),
    )

    async def open_worker():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(
            200, json={"session_id": str(request.session_id), "contract_version": "v4",
                       "state_fingerprint": "a" * 64, "operation_budget": 11,
                       "capabilities": capabilities},
        ))) as client:
            return await HttpVisualWorker(client, "http://worker.test", "fixture").open(request)

    if set(request.required_capabilities) <= set(capabilities):
        assert asyncio.run(open_worker()) == "a" * 64
    else:
        with pytest.raises(VisualWorkerUnavailable, match="capability"):
            asyncio.run(open_worker())
