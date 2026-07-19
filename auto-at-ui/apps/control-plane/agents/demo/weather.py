"""A minimal LangChain tool-calling example exposed through a development API."""

from typing import Any

from langchain.agents import create_agent
from langchain_ollama import ChatOllama


def get_weather(city: str) -> str:
    """Get weather for a given city."""
    return f"It's always sunny in {city}!"


def run_weather_demo(city: str, model: str, base_url: str) -> list[dict[str, Any]]:
    """Run the weather-tool example without persisting its input or model response."""
    chat_model = ChatOllama(
        model=model.removeprefix("ollama:"),
        base_url=base_url,
        temperature=0,
    )
    agent = create_agent(
        model=chat_model,
        tools=[get_weather],
        system_prompt="You are a helpful assistant.",
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": f"What's the weather in {city}?"}]}
    )
    return result["messages"][-1].content_blocks
