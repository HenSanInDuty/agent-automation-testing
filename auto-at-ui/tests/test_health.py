from fastapi.testclient import TestClient
from main import app


def test_health_check() -> None:
    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "control-plane"}
