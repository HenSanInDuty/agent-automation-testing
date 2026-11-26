from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from auto_at.contracts.vision import VisualStateNode
from auto_at.contracts.vision_worker import VisualWorkerOpen
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError


@pytest.mark.parametrize("hops", [10, 20])
def test_worker_and_state_accept_explicit_hop_capacity(hops):
    opened = VisualWorkerOpen(
        tenant_id="fixture", project_id=uuid4(), session_id=uuid4(), fencing_token=1,
        target_url="https://fixture.test", allowed_origins=("https://fixture.test",),
        deadline=datetime.now(UTC) + timedelta(seconds=60), max_session_seconds=60,
        max_states=100, max_hops=hops, max_screenshot_bytes=1024,
    )
    assert opened.max_hops == hops
    assert VisualStateNode(hop=hops, screenshot_checksum="a" * 64).hop == hops
    with pytest.raises(ValidationError):
        VisualWorkerOpen.model_validate(opened.model_dump() | {"max_hops": 21})
    with pytest.raises(ValidationError):
        VisualStateNode(hop=21, screenshot_checksum="a" * 64)


def test_project_policy_capacity_http_round_trip_and_enforcement(monkeypatch):
    from api.v1.routes import generation
    from config import Settings, get_settings

    app = FastAPI()
    app.include_router(generation.router, prefix="/api/v1")
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, codex_bridge_enabled=False,
    )

    saved = {}

    class Repository:
        def __init__(self, _):
            pass

        def set_policy(self, tenant, project, origins, *, vision_owned_test_target=None,
                       **limits):
            # Like the real repository (ADR-046): an omitted flag keeps the stored value.
            previous = saved.get((tenant, project))
            owned = (getattr(previous, "vision_owned_test_target", False)
                     if vision_owned_test_target is None else vision_owned_test_target)
            saved[tenant, project] = SimpleNamespace(
                allowed_origins=origins, vision_owned_test_target=owned, **limits)
            return owned

        def get_policy(self, tenant, project):
            return saved.get((tenant, project))

    monkeypatch.setattr(generation, "SqlAlchemyGenerationRepository", Repository)
    monkeypatch.setattr(generation, "create_session_factory", lambda _: lambda: nullcontext())
    monkeypatch.setattr(generation, "transactional_session", lambda _: nullcontext())
    path = f"/api/v1/test-generations/projects/{uuid4()}/policy"
    headers = {"X-Tenant-Id": "fixture", "X-Actor-Roles": "project_admin"}
    payload = {"allowed_origins": ["https://fixture.test"],
               "vision_max_hops": 20, "vision_max_states": 100}
    with TestClient(app) as client:
        defaults = client.get(path, headers=headers).json()
        assert (defaults["vision_max_hops"], defaults["vision_max_states"]) == (5, 50)
        response = client.put(path, json=payload, headers=headers)
        assert response.status_code == 200, response.text
        stored = payload | {"vision_owned_test_target": False}
        assert response.json() == stored
        assert client.get(path, headers=headers).json() == stored
        owned = client.put(path, json=payload | {"vision_owned_test_target": True},
                           headers=headers)
        assert owned.json()["vision_owned_test_target"] is True
        # A client that does not know the flag cannot reset it.
        assert client.put(path, json=payload, headers=headers).json() == stored | {
            "vision_owned_test_target": True}
        assert client.put(path, json=payload | {"vision_owned_test_target": False},
                          headers=headers).json() == stored
        assert client.put(path, json=payload | {"vision_max_hops": 21},
                          headers=headers).status_code == 422
        assert client.put(path, json=payload | {"vision_max_states": 201},
                          headers=headers).status_code == 422
        assert client.put(path, json=payload, headers=headers | {
            "X-Actor-Roles": "contributor",
        }).status_code == 404
        assert client.get(path, headers=headers).json() == stored
