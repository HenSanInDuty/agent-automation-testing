# Phase 04 — Fluent Bit, Loki, and Grafana Compose stack

## Objective

Collect safe JSON stdout in Fluent Bit, retain it in Loki, and provision Grafana investigations without granting the product dashboard direct log-store authorization.

## Paths and behavior

- Add `observability/fluent-bit/fluent-bit.conf`/parsers: read Docker JSON logs read-only, parse first-party JSON, label only `service`, `environment`, `level`, redact again, and use finite filesystem buffer/retry.
- Add `observability/loki/loki-config.yaml`: local persistent storage, 30-day retention, query limits/compactor, internal-only listener.
- Add Grafana datasource/dashboard provisioning under `observability/grafana/`; query correlation/run/trace/event as JSON fields, not labels.
- Update `docker-compose.yml` with Fluent Bit/Loki/Grafana, data/buffer volumes, health checks; expose only documented local Grafana port. Update `.env.example`, `docs/operations.md`, and add `tests/test_observability_compose.py`.

Run `docker compose config`, focused test, then search an API/run correlation ID in Grafana and prove a secret-shaped fixture is absent. Stop Loki briefly: buffer/retry must be bounded and a run must still finish deterministically. No SSO, tenant log search, trace backend, or production DaemonSet/HA work.
