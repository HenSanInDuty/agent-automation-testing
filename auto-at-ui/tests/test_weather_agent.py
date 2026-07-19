from agents.demo import weather


def test_weather_agent_uses_configured_ollama_endpoint(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeChatOllama:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    class FakeMessage:
        content_blocks = [{"type": "text", "text": "Sunny"}]

    class FakeAgent:
        def invoke(self, payload: object) -> dict[str, list[FakeMessage]]:
            return {"messages": [FakeMessage()]}

    monkeypatch.setattr(weather, "ChatOllama", FakeChatOllama)
    monkeypatch.setattr(weather, "create_agent", lambda **kwargs: FakeAgent())

    assert weather.run_weather_demo(
        "Hanoi",
        "ollama:qwen3:8b-q4_K_M",
        "http://ollama.internal:11434",
    ) == [{"type": "text", "text": "Sunny"}]
    assert captured == {
        "model": "qwen3:8b-q4_K_M",
        "base_url": "http://ollama.internal:11434",
        "temperature": 0,
    }
