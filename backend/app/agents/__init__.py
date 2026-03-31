"""Auto-AT agents package.

Each sub-package corresponds to a pipeline stage:
  - ingestion/   : Pure-Python pipeline (no CrewAI agents)
  - testcase/    : 10 CrewAI agents for test-case generation
  - execution/   : 5  CrewAI agents for test execution
  - reporting/   : 3  CrewAI agents for coverage & reporting
"""
