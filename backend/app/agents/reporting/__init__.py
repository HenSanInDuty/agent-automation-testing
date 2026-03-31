"""Reporting agents sub-package.

Agents:
    coverage_analyzer    – post-execution requirement & scenario coverage
    root_cause_analyzer  – failure pattern grouping & root-cause mapping
    report_generator     – final executive + technical report

All agent configurations (role / goal / backstory / LLM profile) are stored
in the database and managed via the Admin UI.  This package is a namespace
placeholder — actual agent objects are built at runtime by AgentFactory.
"""
