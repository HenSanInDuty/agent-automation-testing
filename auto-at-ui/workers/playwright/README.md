# Playwright worker

This worker is an execution adapter, not the orchestration core. It receives the versioned `TestExecutionRequest` contract, runs a pinned Playwright image, and returns artifacts plus a `TestExecutionResult`.

The transport, container image, and test-suite checkout are intentionally deferred until the control-plane dispatch API is introduced.

