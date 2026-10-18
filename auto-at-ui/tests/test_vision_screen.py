"""Live screenshots are private read-only data, independent of retained evidence."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from api.v1.dependencies.authorization import current_principal, current_tenant
from api.v1.dependencies.vision import vision_screen
from application.vision_replay import VisionReplayNotFoundError
from application.vision_screen import VisionScreen, VisionScreenUnavailable
from domain.authorization import Principal, Role
from fastapi.testclient import TestClient
from main import app

PNG = b"\x89PNG\r\n\x1a\nfixture"


@pytest.mark.parametrize(
    "condition", ["running", "queued", "completed", "missing", "other", "service"],
)
def test_screen_authorizes_before_contacting_worker(condition):
    session_id, project_id = uuid4(), uuid4()
    repository = Mock()
    repository.get.return_value = None if condition == "missing" else SimpleNamespace(
        project_id=project_id, trace_version="v4", fencing_token=7,
        state=condition if condition in {"queued", "completed"} else "running",
    )
    worker = Mock(screen=AsyncMock(return_value=PNG))
    principal = Principal("viewer", {"other" if condition == "other" else "tenant":
                                    frozenset({Role.VIEWER})}, {}, condition == "service")
    call = VisionScreen(repository, worker).read(
        tenant_id="tenant", principal=principal, session_id=session_id,
    )
    if condition in {"missing", "other", "service"}:
        with pytest.raises(VisionReplayNotFoundError):
            asyncio.run(call)
        worker.screen.assert_not_called()
    elif condition == "running":
        assert asyncio.run(call) == PNG
        identity = worker.screen.call_args.args[0]
        assert (identity.tenant_id, identity.project_id, identity.session_id,
                identity.fencing_token) == ("tenant", project_id, session_id, 7)
    else:
        assert asyncio.run(call) is None
        worker.screen.assert_not_called()


@pytest.mark.parametrize("outcome,status", [(PNG, 200), (None, 204),
                                           (VisionScreenUnavailable(), 503),
                                           (VisionReplayNotFoundError(), 404)])
def test_screen_route_returns_private_image_or_safe_status(outcome, status):
    service = Mock(read=AsyncMock())
    if isinstance(outcome, Exception):
        service.read.side_effect = outcome
    else:
        service.read.return_value = outcome
    previous = app.dependency_overrides.copy()
    app.dependency_overrides.update({
        current_tenant: lambda: "tenant",
        current_principal: lambda: Principal("reader", {"tenant": frozenset({Role.VIEWER})}, {}),
        vision_screen: lambda: service,
    })
    try:
        response = TestClient(app).get(f"/api/v1/vision/explorations/{uuid4()}/screen")
        assert response.status_code == status
        if status != 404:
            assert "no-store" in response.headers["cache-control"]
        if status == 200:
            assert response.content == PNG and response.headers["content-type"] == "image/png"
        if status == 204:
            assert not response.content
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
