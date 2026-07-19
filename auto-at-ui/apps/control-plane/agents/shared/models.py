"""Provider-neutral interfaces for LLM integrations.

Concrete LangChain models are configured and injected at the application boundary.
This module must remain free of provider selection and import-time model calls.
"""

from typing import Any, Protocol


class LanguageModel(Protocol):
    """Provider-neutral boundary for a configured LangChain chat model."""

    async def ainvoke(self, payload: Any, **kwargs: Any) -> Any:
        """Invoke the configured model asynchronously."""
        ...
