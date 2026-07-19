# ADR-001: Python control plane with pluggable execution adapters

- Status: Accepted
- Date: 2026-07-19

## Context

The product must begin with Web UI automation and later support API and game testing without rebuilding its orchestration, audit, or agent layers.

## Decision

Use Python managed by `uv` for the control plane, workflows, agents and target-neutral contracts. Use TypeScript for the dashboard and Playwright worker. Define all execution targets behind a target-neutral runner contract.

## Consequences

The system gains access to the Python AI/data ecosystem while retaining first-class Playwright ergonomics. It introduces a service boundary between Python and TypeScript, so contracts must be versioned and workers must be independently deployable.

