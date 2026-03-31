"""Test case generation agents sub-package.

The 10 agents in this stage are managed via the database (AgentConfig rows
seeded by app.db.seed) and built at runtime by app.core.agent_factory.AgentFactory.

Agent IDs (in execution order within TestcaseCrew):
    requirement_analyzer
    scope_classifier
    data_model_agent
    rule_parser
    test_condition_agent
    dependency_agent
    test_case_generator
    automation_agent
    coverage_agent_pre
    report_agent_pre
"""
