from typing import Protocol

from auto_at.contracts.execution import TestExecutionRequest, TestExecutionResult


class ExecutionRunner(Protocol):
    """All target adapters preserve the versioned execution contract."""

    async def execute(self, request: TestExecutionRequest) -> TestExecutionResult: ...
