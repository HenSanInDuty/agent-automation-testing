from fastapi.testclient import TestClient
from main import app


def test_operations_summary_is_authorized_and_returns_every_dashboard_count() -> None:
    response = TestClient(app).get(
        "/api/v1/operations/summary",
        headers={"X-Tenant-Id": "phase-6-empty-tenant", "X-Actor-Roles": "viewer"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "projects": 0,
        "tests": 0,
        "runs": 0,
        "artifacts": 0,
        "proposals": 0,
        "approvals": 0,
        "audit_events": 0,
    }
