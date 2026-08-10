"""Unauthenticated and malformed contracts for dashboard-facing route families."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from main import app


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/auth/me"),
        ("get", "/api/v1/admin/users"),
        ("get", "/api/v1/projects"),
        ("get", f"/api/v1/runs/{uuid4()}"),
        ("get", "/api/v1/activities?run_id=not-a-uuid"),
        ("get", f"/api/v1/test-generations/requests/{uuid4()}"),
        ("get", f"/api/v1/proposals/{uuid4()}"),
    ],
)
def test_dashboard_route_families_reject_unauthenticated_requests(method: str, path: str) -> None:
    response = getattr(TestClient(app), method)(path)

    assert response.status_code in {401, 422}


def test_login_rejects_a_malformed_request_without_disclosing_an_account() -> None:
    response = TestClient(app).post("/api/v1/auth/login", json={})

    assert response.status_code == 422
    assert "email" in str(response.json()["detail"])
