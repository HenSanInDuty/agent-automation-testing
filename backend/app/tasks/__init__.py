"""Auto-AT agent tasks package.

Each sub-module exposes task-factory functions that build ``crewai.Task``
objects for a specific pipeline stage:

    testcase_tasks   – 10 tasks for Test Case Generation crew
    execution_tasks  – 5 tasks for Execution crew
    reporting_tasks  – 3 tasks for Reporting crew

Usage example::

    from app.tasks.testcase_tasks import make_requirement_analyzer_task
    task = make_requirement_analyzer_task(agent, requirements_json)
"""
