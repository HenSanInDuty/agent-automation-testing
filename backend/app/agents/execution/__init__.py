"""Execution stage agents sub-package.

Agents in this stage (all built via AgentFactory from DB config):
    execution_orchestrator  – plans execution order and timeouts
    env_adapter             – resolves target environment configuration
    test_runner             – executes API test cases via api_runner tool
    execution_logger        – aggregates logs and timing statistics
    result_store            – consolidates final ExecutionOutput
"""
