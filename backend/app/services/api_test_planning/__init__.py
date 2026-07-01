"""Adaptive API test-planning services.

Deterministic helpers that support the multi-agent test planner:

* :mod:`complexity`     – score a parsed spec and select 1-5 planner roles.
* :mod:`consolidator`   – extract obligations, fingerprint cases, and merge
                          baseline + agent proposals without losing provenance.
* :mod:`coverage`       – deterministic obligation-to-test coverage score.
* :mod:`review_loop`    – bounded senior-review coverage gate (plan → coverage
                          → review → targeted gap feedback) with deterministic
                          best-iteration selection on exhaustion.
"""
