from config import Settings, get_settings
from fastapi.testclient import TestClient
from main import app


def test_worker_progress_rejects_forged_callback() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        worker_progress_callback_secret="expected-secret"
    )
    try:
        response = TestClient(app).post(
            "/api/v1/internal/worker-progress",
            headers={"X-Worker-Progress-Secret": "forged-secret"},
            json={
                "contract_version": "v1",
                "tenant_id": "tenant-a",
                "run_id": "00000000-0000-4000-8000-000000000001",
                "correlation_id": "00000000-0000-4000-8000-000000000002",
                "stage": "browser.launch",
                "status": "running",
                "safe_summary": "Forged callback.",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
