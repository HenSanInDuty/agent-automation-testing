# Local observability

Fluent Bit reads first-party container stdout, parses JSON records, redacts sensitive-shaped fields again, and forwards to Loki. Grafana is local-only at `http://localhost:3001`; product users have no Grafana or Loki authorization path.

Use the **Auto-AT / Run Investigation** dashboard and enter a correlation or run ID. Those values are JSON fields, never Loki labels. Loki keeps local data for 30 days. Fluent Bit has a finite filesystem buffer and bounded retries: a collector or Loki failure is observable but cannot alter a deterministic run verdict.

For production, choose Grafana authentication/RBAC, alert routing, TLS, and a durable Loki topology before exposing any endpoint.
