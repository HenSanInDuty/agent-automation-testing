from api.v1.routes import demo
from fastapi.testclient import TestClient
from main import app


def test_weather_demo_returns_model_content_blocks(monkeypatch) -> None:
    monkeypatch.setattr(
        demo,
        "run_weather_demo",
        lambda city, model, base_url: [{"type": "text", "text": f"Sunny in {city}"}],
    )

    response = TestClient(app).post("/api/v1/demo/weather", json={"city": "Hanoi"})

    assert response.status_code == 200
    assert response.json() == {"content_blocks": [{"type": "text", "text": "Sunny in Hanoi"}]}
